"""Estrazione del testo da un questionario grezzo: Word, PDF, Excel, testo.

L'obiettivo non è una conversione fedele ma un testo leggibile dall'agente
importatore, con l'ordine del documento conservato e marcatori di pagina o
foglio che aiutano a ritrovare il punto nel sorgente. Nessun OCR: un PDF
scansionato senza livello di testo viene rifiutato con un errore chiaro.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

FORMATS: dict[str, str] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".txt": "text",
    ".md": "text",
}
MAX_CHARS = 400_000  # oltre questa soglia il documento è sospetto (allegati, dati grezzi)


class ExtractionError(Exception):
    """Il file non può essere letto o non contiene testo utilizzabile."""


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    sha256: str
    format: str
    text: str
    units: int  # pagine (PDF), fogli (Excel) o 1
    warnings: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.text)


def _tidy(text: str) -> str:
    """Spazi multipli e righe vuote ripetute compresse; niente spazi in coda."""
    righe = [re.sub("[ \\t\\xa0]+", " ", r).strip() for r in text.splitlines()]
    out: list[str] = []
    for r in righe:
        if r or (out and out[-1]):
            out.append(r)
    return "\n".join(out).strip() + "\n"


def _from_docx(path: Path) -> tuple[str, int, list[str]]:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    righe: list[str] = []
    avvisi: list[str] = []
    liste = 0
    for el in doc.element.body.iterchildren():
        if el.tag == qn("w:p"):
            par = Paragraph(el, doc)
            testo = par.text
            if not testo.strip():
                righe.append("")
                continue
            stile = (par.style.name if par.style is not None else "") or ""
            numerato = el.find(".//" + qn("w:numPr")) is not None or "Number" in stile
            if stile.startswith("Heading") or stile.startswith("Titolo"):
                righe.append(f"## {testo}")
            elif numerato or "List" in stile or "Elenco" in stile:
                liste += numerato
                righe.append(f"- {testo}")
            else:
                righe.append(testo)
        elif el.tag == qn("w:tbl"):
            tab = Table(el, doc)
            for row in tab.rows:
                celle = [" ".join(c.text.split()) for c in row.cells]
                # Celle unite compaiono ripetute: le deduplichiamo in sequenza.
                uniche = [c for i, c in enumerate(celle) if i == 0 or c != celle[i - 1]]
                while uniche and not uniche[-1]:
                    uniche.pop()
                righe.append(" | ".join(uniche))
            righe.append("")
    if liste:
        avvisi.append(
            f"{liste} voci di elenco numerato: Word non conserva i numeri nel testo, "
            "controllare i riferimenti alle domande nelle istruzioni di salto"
        )
    return "\n".join(righe), 1, avvisi


def _from_pdf(path: Path) -> tuple[str, int, list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("PDF protetto da password")
        pagine = [(p.extract_text() or "") for p in reader.pages]
    except PdfReadError as exc:
        raise ExtractionError(f"PDF non leggibile: {exc}") from exc
    vuote = [i + 1 for i, t in enumerate(pagine) if not t.strip()]
    if len(vuote) == len(pagine):
        raise ExtractionError(
            "il PDF non contiene testo estraibile (scansione?): l'OCR non è supportato"
        )
    avvisi = []
    if vuote:
        avvisi.append(f"pagine senza testo: {', '.join(map(str, vuote))}")
    blocchi = [f"=== Pagina {i + 1} ===\n{t}" for i, t in enumerate(pagine)]
    return "\n\n".join(blocchi), len(pagine), avvisi


def _from_xlsx(path: Path) -> tuple[str, int, list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    blocchi: list[str] = []
    for ws in wb.worksheets:
        righe = [f'=== Foglio "{ws.title}" ===']
        for row in ws.iter_rows(values_only=True):
            celle = ["" if v is None else str(v).strip() for v in row]
            while celle and not celle[-1]:
                celle.pop()
            if any(celle):
                righe.append(" | ".join(celle))
        blocchi.append("\n".join(righe))
    wb.close()
    testo = "\n\n".join(blocchi)
    if not any(line and not line.startswith("=== Foglio") for line in testo.splitlines()):
        raise ExtractionError("il file Excel non contiene celle con testo")
    return testo, len(wb.worksheets), []


def _from_text(path: Path) -> tuple[str, int, list[str]]:
    dati = path.read_bytes()
    try:
        return dati.decode("utf-8-sig"), 1, []
    except UnicodeDecodeError:
        return dati.decode("cp1252"), 1, ["file non UTF-8: letto come Windows-1252"]


def extract_text(path: Path | str) -> ExtractedDocument:
    """Legge il file in base all'estensione e restituisce il testo con hash e avvisi."""
    path = Path(path)
    if not path.is_file():
        raise ExtractionError(f"file non trovato: {path}")
    fmt = FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ExtractionError(
            f"formato '{path.suffix}' non supportato; ammessi: {', '.join(sorted(FORMATS))}"
        )
    lettori = {"docx": _from_docx, "pdf": _from_pdf, "xlsx": _from_xlsx, "text": _from_text}
    try:
        grezzo, unita, avvisi = lettori[fmt](path)
    except ExtractionError:
        raise
    except Exception as exc:  # librerie di terze parti: errori eterogenei
        raise ExtractionError(f"impossibile leggere {path.name}: {exc}") from exc
    testo = _tidy(grezzo)
    if not testo.strip():
        raise ExtractionError(f"nessun testo trovato in {path.name}")
    if len(testo) > MAX_CHARS:
        avvisi.append(
            f"testo molto lungo ({len(testo)} caratteri): verificare che sia solo il questionario"
        )
    return ExtractedDocument(
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        format=fmt,
        text=testo,
        units=unita,
        warnings=avvisi,
    )
