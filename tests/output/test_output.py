"""Output di M10: dataset largo, .sav, codebook, report HTML, analisi, CLI report."""

import json
from pathlib import Path
from typing import Any

import polars as pl
import pyreadstat
import pytest
import yaml
from typer.testing import CliRunner

from synthsurvey.cli import app
from synthsurvey.config import load_config
from synthsurvey.llm import FakeLLMClient, LLMPool, default_pricing
from synthsurvey.output import (
    MISSING,
    OutputError,
    build_wide,
    compare,
    load_run,
    replicate_stability,
    status_by_mode,
    straightlining,
    summarize,
    write_outputs,
)
from synthsurvey.personas.build import personas_frame
from synthsurvey.population.tables import load_tables
from synthsurvey.runner import FrozenError, execute_run, freeze_run
from tests.config.conftest import ESEMPI_DIR

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
runner = CliRunner()


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Un pilota 12 persone x 3 modalità x 2 repliche con il client finto, output compresi."""
    tmp = tmp_path_factory.mktemp("run")
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["engine"]["replicates"] = 2
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp / "runs")
    path = tmp / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    pools = [LLMPool(FakeLLMClient("fake-1"), pricing=default_pricing(0.92))]
    result = execute_run(
        load_config(path),
        data_dir=PROCESSED.parent,
        pilot=True,
        run_id="pilota",
        tables=load_tables(PROCESSED),
        pools=pools,
    )
    return result.run_dir


def test_il_run_produce_gli_output_di_m10(run_dir: Path) -> None:
    for nome in (
        "responses_wide.parquet",
        "responses_wide.csv",
        "responses_wide.sav",
        "codebook.json",
        "report.html",
        "interviste.html",
    ):
        assert (run_dir / nome).is_file(), nome


def test_dataset_largo(run_dir: Path) -> None:
    _manifest, long, personas, q = load_run(run_dir)
    wide, variables = build_wide(long, personas_frame(personas), q)
    assert wide.height == 12 * 3 * 2
    nomi = [v.name for v in variables]
    assert nomi[:3] == ["q1", "q2", "q3"]
    assert "q4_1" in nomi and "q4_6" in nomi and "q5_a" in nomi and "q5_c" in nomi
    assert "q7" in nomi and "q7_status" in nomi and nomi.index("q6") < nomi.index("q7")
    for col in ("segment", "region", "sex", "age", "weight", "weight_pop", "size_class"):
        assert col in wide.columns
    # Il client finto sceglie sempre la prima opzione / il primo punto.
    consumer = wide.filter(pl.col("segment") == "consumer")
    assert set(consumer["q1"].unique().to_list()) == {1}
    assert set(consumer["q8"].unique().to_list()) == {MISSING["not_applicable"]}, "solo pmi"
    assert set(consumer["q5_a"].unique().to_list()) == {1}
    assert consumer["q4_1"].max() == 1 and consumer["q4_6"].max() <= 1
    assert consumer["q7_status"].min() >= 0
    assert wide.schema["q6"] == pl.Float64 and wide.schema["q7"] == pl.String
    assert wide.select(["persona_id", "mode", "replicate", "model"]).unique().height == wide.height


def test_sav_si_rilegge_con_etichette(run_dir: Path) -> None:
    df, meta = pyreadstat.read_sav(str(run_dir / "responses_wide.sav"), user_missing=True)
    assert len(df) == 72 and "q1" in df.columns and "weight" in df.columns
    assert meta.file_label.startswith("synthsurvey: dati SIMULATI")
    etichette = dict(zip(meta.column_names, meta.column_labels, strict=True))
    assert etichette["q1"].startswith("Quanto è soddisfatto")
    assert etichette["q5_a"].endswith("[Le bollette sono facili da capire]")
    assert meta.variable_value_labels["q2"][1.0] == "Prezzo"
    assert meta.variable_value_labels["q1"][-3.0].startswith("Non so")
    assert meta.missing_ranges["q1"][0]["lo"] == -4.0
    assert isinstance(df["q7"].iloc[0], str) and df["mode"].iloc[0] in ("cawi", "cati", "capi")


def test_codebook(run_dir: Path) -> None:
    cb = json.loads((run_dir / "codebook.json").read_text(encoding="utf-8"))
    assert cb["run_id"] == "pilota" and "SIMULATI" in cb["disclaimer"]
    assert cb["questionnaire"]["id"] == "mercato_v1" and cb["questionnaire"]["sha256"]
    assert cb["missing_codes"]["-3"].startswith("Non so")
    nomi = [v["name"] for v in cb["wide"]["variables"]]
    assert "q4_2" in nomi and "q5_b" in nomi
    q2 = next(v for v in cb["wide"]["variables"] if v["name"] == "q2")
    assert q2["values"]["4"] == "Altro" and q2["missing"]["-1"] == "Non applicabile"
    prov = {p["name"]: p for p in cb["persona_traits_provenance"]}
    assert prov["sensibilita_prezzo"]["provenance"] == "ipotesi"
    assert "IPOTESI" in prov["sensibilita_prezzo"]["provenance_note"]
    assert cb["long"]["columns"][0] == "run_id"


def test_report_html(run_dir: Path) -> None:
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "DATI SIMULATI" in html and "<svg" in html
    for titolo in (
        "1. Esito delle interviste",
        "2. Distribuzioni per domanda",
        "3. Effetti di modalità",
        "4. Confronto fra segmenti",
        "5. Stabilità fra repliche",
        "6. Segnali non verbali",
        "7. Costi e chiamate",
    ):
        assert titolo in html, titolo
    assert "<h3>q1</h3>" in html and "Straightlining" in html
    assert "fake/fake-1" in html and "pilota" in html


def _dati_pagina(html: str) -> dict[str, Any]:
    inizio = html.index("const D = ") + len("const D = ")
    fine = html.index(";</script>", inizio)
    return json.loads(html[inizio:fine])


def test_pagina_interviste(run_dir: Path) -> None:
    html = (run_dir / "interviste.html").read_text(encoding="utf-8")
    assert "DATI SIMULATI" in html and "Per domanda" in html and "Per persona" in html
    assert "<link" not in html and 'src="http' not in html, (
        "pagina autonoma, niente risorse esterne"
    )
    dati = _dati_pagina(html)
    _manifest, long, personas, q = load_run(run_dir)
    assert len(dati["rows"]) == long.height
    assert dati["modes"] == ["cawi", "cati", "capi"] and dati["replicates"] == [1, 2]
    assert [x["id"] for x in dati["questions"]] == [x.id for s in q.sections for x in s.questions]
    assert len(dati["personas"]) == len(personas) and len(dati["interviews"]) == 72
    assert all(i["completed"] for i in dati["interviews"])
    for p in personas:
        assert p.unit_id not in html, "nessun legame con i record del committente"
    griglia = [r for r in dati["rows"] if r["q"] == "q5"]
    testi = {i.text for s in q.sections for x in s.questions if x.id == "q5" for i in x.items or []}
    assert griglia and all(r["i"] in testi for r in griglia), "righe della griglia col loro testo"


def test_segnali_non_verbali_della_pagina() -> None:
    from synthsurvey.output.interviews import _nonverbal

    livelli, pensiero = _nonverbal(
        json.dumps({"esitazione": 2, "entusiasmo": 0, "imbarazzo": 1, "body": {}, "note": "Uffa."})
    )
    assert livelli == {"esitazione": 2, "imbarazzo": 1} and pensiero == "Uffa."
    assert _nonverbal(None) == ({}, "") and _nonverbal("non json") == ({}, "")


def test_analisi(run_dir: Path) -> None:
    _manifest, long, personas, q = load_run(run_dir)
    wide, variables = build_wide(long, personas_frame(personas), q)
    q1 = next(v for v in variables if v.name == "q1")
    tutti = summarize(wide, q1)["tutti"]
    assert tutti.n == 72 and tutti.mean == 1.0 and tutti.shares == {"Per nulla": pytest.approx(1.0)}
    per_modo = summarize(wide, q1, by="mode")
    assert set(per_modo) == {"cawi", "cati", "capi"} and per_modo["cati"].n == 24
    q8 = next(v for v in variables if v.name == "q8")
    per_segmento = summarize(wide, q8, by="segment")
    assert per_segmento["consumer"].n == 0 and per_segmento["consumer"].missing_shares == {
        "Non applicabile": 1.0
    }
    assert per_segmento["pmi"].n > 0
    effetti = compare(wide, variables, "mode", reference="cawi")
    e1 = next(e for e in effetti if e["name"] == "q1")
    assert e1["reference"] == "cawi" and e1["groups"]["cati"]["delta"] == 0.0
    assert e1["groups"]["cawi"]["metric"] == "media"
    e2 = next(e for e in effetti if e["name"] == "q2")
    assert e2["groups"]["cawi"]["metric"].startswith("quota «")
    stabile = replicate_stability(wide, variables)
    accordo = {s["name"]: s["agreement"] for s in stabile}
    assert accordo["q1"] == 1.0 and accordo["q3"] == 1.0, "domande non randomizzate"
    assert any(v < 1.0 for k, v in accordo.items() if k.startswith("q4_")), "q4 ruota"
    piatte = straightlining(wide, variables)
    assert piatte[0]["question_id"] == "q5" and piatte[0]["by_mode"]["cawi"]["rate"] == 1.0
    stati = status_by_mode(long)
    assert stati["cawi"]["answered"] > 0.9


def test_output_su_run_congelato_e_errori(run_dir: Path, tmp_path: Path) -> None:
    freeze_run(run_dir)
    with pytest.raises(FrozenError):
        write_outputs(run_dir)
    altrove = tmp_path / "out"
    result = write_outputs(run_dir, out_dir=altrove, formats=["csv"])
    assert (altrove / "responses_wide.csv").is_file() and not (
        altrove / "responses_wide.sav"
    ).exists()
    assert (altrove / "report.html").is_file() and result.wide is not None
    assert (altrove / "interviste.html").is_file(), "anche da un run congelato, altrove"
    with pytest.raises(OutputError, match="manifest assente"):
        write_outputs(tmp_path / "vuota")
    with pytest.raises(OutputError, match="questionario non trovato"):
        write_outputs(run_dir, out_dir=altrove, questionnaire_path=tmp_path / "manca.yaml")


def test_cli_report(run_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "rep"
    result = runner.invoke(app, ["report", str(run_dir), "--out", str(out), "--formats", "csv,sav"])
    assert result.exit_code == 0, result.output
    assert "report.html" in result.output and "72 righe larghe" in result.output
    assert (out / "responses_wide.sav").is_file()
    errore = runner.invoke(app, ["report", str(tmp_path / "niente")])
    assert errore.exit_code == 1 and "manifest assente" in errore.output
    congelato = runner.invoke(app, ["report", str(run_dir)])
    assert congelato.exit_code == 1 and "congelato" in congelato.output


def _unused(_: Any) -> None:  # pragma: no cover
    return None
