"""Estrazione del testo da Word, PDF, Excel e testo semplice."""

from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from pypdf import PdfWriter

from synthsurvey.questionnaire import ExtractionError, extract_text
from synthsurvey.questionnaire.extract import FORMATS, MAX_CHARS, _tidy

ROOT = Path(__file__).resolve().parents[2]
DOCX = ROOT / "questionnaires" / "examples" / "mercato_v1.docx"
PDF = Path(__file__).resolve().parent / "fixtures" / "questionario.pdf"


def test_word_di_esempio_conserva_ordine_titoli_opzioni_e_tabella() -> None:
    doc = extract_text(DOCX)
    assert doc.format == "docx" and doc.units == 1 and len(doc.sha256) == 64
    t = doc.text
    assert "## Sezione A. Fornitura di energia" in t
    assert t.index("D1. Quanto è soddisfatto") < t.index("D2. Qual è il motivo")
    assert "- Trasparenza della bolletta" in t, "le voci di elenco hanno il trattino"
    assert "Se No, passare alla D5." in t
    assert "Affermazione | 1 | 2 | 3 | 4 | 5" in t, "la griglia è una tabella"
    assert "Le bollette sono facili da capire\n" in t, "celle vuote in coda eliminate"
    assert "Grazie per la collaborazione." in t
    assert doc.warnings == []


def test_word_elenco_numerato_avvisa(tmp_path: Path) -> None:
    d = Document()
    d.add_paragraph("D1. Domanda")
    d.add_paragraph("Prima", style="List Number")
    d.add_paragraph("Seconda", style="List Number")
    path = tmp_path / "num.docx"
    d.save(str(path))
    doc = extract_text(path)
    assert "- Prima\n- Seconda" in doc.text
    assert doc.warnings and "elenco numerato" in doc.warnings[0]


def test_pdf_con_marcatori_di_pagina() -> None:
    doc = extract_text(PDF)
    assert doc.format == "pdf" and doc.units == 2
    assert "=== Pagina 1 ===" in doc.text and "=== Pagina 2 ===" in doc.text
    assert "Indagine sulla mobilità urbana" in doc.text, "WinAnsi decodificato"
    assert doc.text.index("D2.") < doc.text.index("=== Pagina 2 ===") < doc.text.index("D3. Quanto")


def test_pdf_senza_testo_rifiutato(tmp_path: Path) -> None:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    path = tmp_path / "scan.pdf"
    with path.open("wb") as fh:
        w.write(fh)
    with pytest.raises(ExtractionError, match="OCR"):
        extract_text(path)


def test_pdf_corrotto(tmp_path: Path) -> None:
    path = tmp_path / "rotto.pdf"
    path.write_bytes(b"%PDF-1.4\nnon un pdf")
    with pytest.raises(ExtractionError):
        extract_text(path)


def test_excel_fogli_e_righe(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Domande"
    ws.append(["D1", "Quanto è soddisfatto?", "scala 1-10"])
    ws.append([None, None, None])
    ws.append(["D2", "Perché?", None, None])
    altro = wb.create_sheet("Quote")
    altro.append(["sesso", 50])
    path = tmp_path / "q.xlsx"
    wb.save(str(path))
    doc = extract_text(path)
    assert doc.format == "xlsx" and doc.units == 2
    atteso = '=== Foglio "Domande" ===\nD1 | Quanto è soddisfatto? | scala 1-10\nD2 | Perché?'
    assert atteso in doc.text
    assert '=== Foglio "Quote" ===\nsesso | 50' in doc.text


def test_excel_vuoto(tmp_path: Path) -> None:
    path = tmp_path / "vuoto.xlsx"
    Workbook().save(str(path))
    with pytest.raises(ExtractionError, match="celle"):
        extract_text(path)


def test_testo_utf8_e_cp1252(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    a.write_text("D1. Perché?\n\n\n\nD2.  Sì  ", encoding="utf-8")
    doc = extract_text(a)
    assert doc.text == "D1. Perché?\n\nD2. Sì\n" and doc.warnings == []
    b = tmp_path / "b.md"
    b.write_bytes("D1. Perché?".encode("cp1252"))
    doc_b = extract_text(b)
    assert doc_b.text == "D1. Perché?\n" and "Windows-1252" in doc_b.warnings[0]


def test_testo_vuoto_e_lungo(tmp_path: Path) -> None:
    vuoto = tmp_path / "v.txt"
    vuoto.write_text("   \n\n", encoding="utf-8")
    with pytest.raises(ExtractionError, match="nessun testo"):
        extract_text(vuoto)
    lungo = tmp_path / "l.txt"
    lungo.write_text("x" * (MAX_CHARS + 1), encoding="utf-8")
    assert "molto lungo" in extract_text(lungo).warnings[0]


def test_formato_ignoto_e_file_mancante(tmp_path: Path) -> None:
    odt = tmp_path / "q.odt"
    odt.write_text("x", encoding="utf-8")
    with pytest.raises(ExtractionError, match="non supportato"):
        extract_text(odt)
    with pytest.raises(ExtractionError, match="non trovato"):
        extract_text(tmp_path / "manca.docx")
    assert set(FORMATS) >= {".docx", ".pdf", ".xlsx", ".txt", ".md"}


def test_tidy() -> None:
    assert _tidy("a \t b\xa0c\n\n\n d \n") == "a b c\n\nd\n"
    assert _tidy("\n\nx") == "x\n"
