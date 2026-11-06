"""Genera i questionari grezzi di esempio usati da `questionnaire import` e dai test.

- questionnaires/examples/mercato_v1.docx: un questionario come lo scrive un
  istituto, con istruzioni di salto in prosa, scale, griglia e note per
  l'intervistatore. È il caso di prova della milestone M6b.
- tests/questionnaire/fixtures/questionario.pdf: PDF minimo scritto a mano
  (nessuna libreria di scrittura PDF nel progetto) con due pagine di testo.

Eseguire con: uv run python scripts/make_questionnaire_fixtures.py
"""

from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "questionnaires" / "examples" / "mercato_v1.docx"
PDF = ROOT / "tests" / "questionnaire" / "fixtures" / "questionario.pdf"


def make_docx(path: Path) -> None:
    doc = Document()
    stile = doc.styles["Normal"]
    stile.font.name = "Calibri"
    stile.font.size = Pt(11)
    doc.add_heading("Indagine sulla fornitura di energia 2026", level=1)
    doc.add_paragraph(
        "Questionario versione 1.1. Rivolto a consumatori e piccole e medie imprese. "
        "Durata prevista 8 minuti. Le domande D8 e D9 si fanno solo ai rispondenti "
        "che parlano per conto di un'impresa."
    )
    doc.add_heading("Sezione A. Fornitura di energia", level=2)

    doc.add_paragraph("D1. Quanto è soddisfatto del suo attuale fornitore di energia?")
    doc.add_paragraph(
        "Scala da 1 a 10, dove 1 significa “per nulla” e 10 “del tutto”. Ammesso “non so”."
    )

    doc.add_paragraph("D2. Qual è il motivo principale della sua insoddisfazione?")
    doc.add_paragraph("(Solo a chi ha dato un voto da 1 a 5 alla D1. Una sola risposta, ruotare)")
    for o in ["Prezzo", "Servizio clienti", "Trasparenza della bolletta", "Altro (specificare)"]:
        doc.add_paragraph(o, style="List Bullet")

    doc.add_paragraph("D3. Negli ultimi 12 mesi ha provato a cambiare fornitore?")
    for o in ["Sì, ho cambiato", "Ci ho provato ma non ho cambiato", "No"]:
        doc.add_paragraph(o, style="List Bullet")
    doc.add_paragraph("Se No, passare alla D5.")

    doc.add_paragraph("D4. Quali di questi canali ha usato per informarsi sulle offerte?")
    doc.add_paragraph("(Massimo tre risposte; ruotare le voci tenendo “Nessuno” in fondo)")
    for o in [
        "Sito del fornitore",
        "Comparatori online",
        "Passaparola",
        "Punto vendita",
        "Pubblicità",
        "Nessuno",
    ]:
        doc.add_paragraph(o, style="List Bullet")

    doc.add_heading("Sezione B. Giudizi", level=2)
    doc.add_paragraph("D5. Quanto è d'accordo con le seguenti affermazioni?")
    doc.add_paragraph(
        "Per ogni riga un voto da 1 “per niente d'accordo” a 5 “del tutto d'accordo”; "
        "ammesso “non so”."
    )
    tab = doc.add_table(rows=1, cols=6)
    tab.style = "Table Grid"
    intest = tab.rows[0].cells
    intest[0].text = "Affermazione"
    for i in range(1, 6):
        intest[i].text = str(i)
    for riga in [
        "Le bollette sono facili da capire",
        "Cambiare fornitore è semplice",
        "Le offerte sono trasparenti",
    ]:
        celle = tab.add_row().cells
        celle[0].text = riga
    doc.add_paragraph("")
    doc.add_paragraph(
        "D6. Quanto spende in media al mese per l'energia? Indicare l'importo in euro."
    )
    doc.add_paragraph("|__|__|__|__| euro            Non so")
    doc.add_paragraph("D7. Ha qualche suggerimento per il suo fornitore? (Risposta libera)")
    doc.add_paragraph("Fare la D7 solo a chi ha dato un voto fino a 7 alla D1.")

    doc.add_heading("Sezione C. Solo imprese", level=2)
    doc.add_paragraph("D8. Nella sua impresa chi decide il fornitore di energia?")
    for o in ["Il titolare", "L'amministrazione", "Un consulente esterno", "Altro"]:
        doc.add_paragraph(o, style="List Bullet")
    doc.add_paragraph("D9. Negli ultimi tre anni la spesa energetica dell'impresa è...")
    for o in ["Aumentata molto", "Aumentata un po'", "Rimasta stabile", "Diminuita"]:
        doc.add_paragraph(o, style="List Bullet")
    doc.add_paragraph("D10. Quale fascia di reddito familiare netto mensile la descrive meglio?")
    doc.add_paragraph("(A tutti. Domanda sensibile: leggere “preferisce non rispondere”)")
    for o in ["Fino a 1.500 euro", "1.501-2.500 euro", "2.501-4.000 euro", "Oltre 4.000 euro"]:
        doc.add_paragraph(o, style="List Bullet")
    doc.add_paragraph("Grazie per la collaborazione.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def _pdf_text_stream(lines: list[str]) -> bytes:
    """Flusso di contenuto: una riga di testo ogni 16 punti, font Helvetica 11."""
    parti = ["BT", "/F1 11 Tf", "16 TL", "50 780 Td"]
    for i, line in enumerate(lines):
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        parti.append(("" if i == 0 else "T* ") + f"({esc}) Tj")
    parti.append("ET")
    return "\n".join(parti).encode("cp1252")


def make_pdf(path: Path, pages: list[list[str]]) -> None:
    objs: list[bytes] = []
    n_pages = len(pages)
    # 1 catalogo, 2 pagine, 3 font, poi per pagina: pagina e contenuto.
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    for i, lines in enumerate(pages):
        page_id, content_id = 4 + 2 * i, 5 + 2 * i
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        stream = _pdf_text_stream(lines)
        testa = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        objs.append(testa + stream + b"\nendstream")
        assert page_id == len(objs) - 1
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


PDF_PAGES = [
    [
        "Indagine sulla mobilità urbana",
        "D1. Con quale mezzo si sposta più spesso per andare al lavoro?",
        "- Auto propria",
        "- Mezzi pubblici",
        "- Bicicletta o a piedi",
        "- Non lavoro fuori casa",
        "Se Non lavoro fuori casa, passare alla D3.",
        "D2. Quanti minuti impiega in media? Indicare un numero.",
    ],
    [
        "D3. Quanto è soddisfatto dei trasporti pubblici della sua città?",
        "Scala da 1 (per nulla) a 5 (del tutto). Ammesso non so.",
        "Grazie.",
    ],
]

if __name__ == "__main__":
    make_docx(DOCX)
    make_pdf(PDF, PDF_PAGES)
    print(f"scritti {DOCX} e {PDF}")
