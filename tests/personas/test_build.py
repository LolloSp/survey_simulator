"""Costruzione delle persone: coerenza, determinismo, narrativa, provenienze, CLI."""

import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from survey_simulator.cli import app
from survey_simulator.config import SurveySimulatorConfig, load_config
from survey_simulator.personas import PersonasResult, Provenance, build_personas, personas_markdown
from survey_simulator.personas.coherence import hard_violations, sample_warnings
from survey_simulator.personas.narrative import REGION_NAMES, render_narrative, template_hash
from survey_simulator.population import categories as cat
from survey_simulator.population.sample import SampleResult, build_sample
from survey_simulator.population.tables import IstatTables
from tests.config.conftest import ESEMPI_DIR
from tests.personas.conftest import PROCESSED


@pytest.fixture(scope="module")
def result(
    sample_100: SampleResult, config_100: SurveySimulatorConfig, tables: IstatTables
) -> PersonasResult:
    return build_personas(sample_100, config_100, tables, processed_dir=PROCESSED)


def test_una_persona_per_unita(result: PersonasResult, sample_100: SampleResult) -> None:
    assert len(result.personas) == sample_100.units.height
    assert [p.unit_id for p in result.personas] == sample_100.units["unit_id"].to_list()
    assert len({p.persona_id for p in result.personas}) == len(result.personas)
    assert result.frame.height == len(result.personas)
    assert "narrative" in result.frame.columns


def test_coerenza_e_provenienze(result: PersonasResult) -> None:
    for p in result.personas:
        attrs = {**p.model_dump(), **p.attitudes.model_dump(), **p.response_style.model_dump()}
        if p.firm:
            attrs.update(p.firm.model_dump())
        assert hard_violations(attrs) == [], (p.persona_id, hard_violations(attrs))
        assert p.provenance["trust"] is Provenance.ISTAT
        assert p.provenance["sensibilita_prezzo"] is Provenance.IPOTESI
        if p.firm:
            assert p.provenance["respondent_role"] is Provenance.IPOTESI
            assert p.firm.respondent_role in {"titolare", "responsabile_acquisti", "amministratore"}
            assert p.employment == "occupato"
        else:
            assert p.provenance["age"] is Provenance.CAMPIONE
        assert "template" in p.source_versions and p.source_versions["template"] == template_hash()
        assert "trust_sex_ageclass_education" in p.source_versions
    assert set(result.diagnostics["provenienze"]) >= {"campione", "istat", "ipotesi"}


def test_narrativa_contiene_i_fatti(result: PersonasResult) -> None:
    for p in result.personas:
        n = p.narrative
        assert "{" not in n and "}" not in n, "nessun segnaposto"
        assert REGION_NAMES[p.region] in n
        assert str(p.age) in n
        assert p.name is not None and n.startswith(p.name)
        assert 80 <= len(n.split()) <= 220, len(n.split())
        if p.firm:
            assert str(p.firm.employees) in n
        assert render_narrative(p) == n


def test_determinismo(
    sample_100: SampleResult,
    config_100: SurveySimulatorConfig,
    tables: IstatTables,
    result: PersonasResult,
) -> None:
    bis = build_personas(sample_100, config_100, tables, processed_dir=PROCESSED)
    assert bis.frame.equals(result.frame)
    altro = config_100.model_copy(
        update={"project": config_100.project.model_copy(update={"seed": 7})}
    )
    campione_altro = build_sample(altro, PROCESSED, tables=tables)
    ter = build_personas(campione_altro, altro, tables)
    assert not ter.frame.drop("narrative").equals(result.frame.drop("narrative"))


def test_senza_nomi(
    sample_100: SampleResult, config_100: SurveySimulatorConfig, tables: IstatTables
) -> None:
    cfg = config_100.model_copy(
        update={"personas": config_100.personas.model_copy(update={"include_names": False})}
    )
    res = build_personas(sample_100, cfg, tables)
    assert all(p.name is None for p in res.personas)
    assert res.personas[0].narrative.startswith(("Un uomo", "Una donna"))


def test_distribuzioni_su_campione_grande(tables: IstatTables) -> None:
    """Su 1000 persone le quote degli attributi ISTAT restano vicine alle tavole."""
    cfg = load_config(ESEMPI_DIR / "mercato_1000.yaml").config
    sample = build_sample(cfg, PROCESSED, tables=tables)
    res = build_personas(sample, cfg, tables)
    consumer = res.frame.filter(pl.col("segment") == "consumer")
    quota_fiducia = (consumer["trust"] == "si_fida").mean()
    attesa = (
        tables.trust.filter(pl.col("category") == "si_fida")["count"].sum()
        / tables.trust["count"].sum()
    )
    assert abs(float(quota_fiducia) - float(attesa)) < 0.06
    assert 0.6 < float((consumer["internet"] == "quotidiano").mean()) < 0.9
    pmi = res.frame.filter(pl.col("segment") == "pmi")
    # La config 1000 ammette anche il ruolo "altro".
    assert pmi["respondent_role"].is_in(list(cat.RESPONDENT_ROLES)).all()
    assert pmi["respondent_role"].is_in(["altro"]).any()
    assert pmi.filter(pl.col("size_class") == "media")["employees"].min() >= 50


def test_regole_di_coerenza() -> None:
    assert hard_violations({"life_satisfaction": 1, "economic_judgement": "ottime"})
    assert hard_violations({"life_satisfaction": 10, "economic_judgement": "insufficienti"})
    assert hard_violations({"internet": "mai", "apertura_novita": 0.9})
    assert hard_violations({"employment": "in_cerca", "income_quintile": 5, "age": 22})
    assert hard_violations({"respondent_role": "responsabile_acquisti", "employees": 2})
    assert (
        hard_violations(
            {
                "life_satisfaction": 7,
                "economic_judgement": "adeguate",
                "internet": "quotidiano",
                "apertura_novita": 0.5,
            }
        )
        == []
    )
    assert sample_warnings({"age": 40, "employment": "pensionato"}) == [
        "pensionato sotto i 50 anni"
    ]
    assert sample_warnings({"age": 60, "employment": "pensionato", "education": "diploma"}) == []


def test_markdown_di_revisione(result: PersonasResult) -> None:
    md = personas_markdown(result.personas[:3])
    assert md.startswith("# Persone generate")
    assert md.count("## p_") == 3
    assert "tratti (ipotesi)" in md


def test_cli_personas_preview(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "personas",
            "preview",
            "--config",
            str(ESEMPI_DIR / "mercato_100.yaml"),
            "--data-dir",
            str(PROCESSED.parent),
            "--n",
            "10",
            "--out",
            str(tmp_path),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "Persone per indagine-mercato-2026" in res.output
    assert "Provenienze:" in res.output
    personas = json.loads((tmp_path / "personas.json").read_text(encoding="utf-8"))
    assert len(personas) == 10
    assert (tmp_path / "personas.md").is_file()
    assert pl.read_csv(tmp_path / "personas.csv").height == 10


def test_eufonia() -> None:
    from survey_simulator.personas.narrative import eufonia

    assert eufonia("è diplomato e è in pensione") == "è diplomato ed è in pensione"
    assert eufonia("ha puntato a ampliare la gamma") == "ha puntato ad ampliare la gamma"
    assert eufonia("sa che è così e che a Roma piove") == "sa che è così e che a Roma piove"
    assert eufonia("vive e lavora") == "vive e lavora"
