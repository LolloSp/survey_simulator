"""Versioni per modalità, ordine delle opzioni, esportazione e CLI."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from typer.testing import CliRunner

from synthsurvey.cli import app
from synthsurvey.questionnaire import (
    DONT_KNOW_LABEL,
    Mode,
    Questionnaire,
    QuestionType,
    adapt,
    adapt_all,
    export,
    option_order,
    parse_questionnaire,
    to_markdown,
    to_yaml,
)
from tests.config.conftest import ESEMPI_DIR
from tests.questionnaire.conftest import ESEMPIO, domanda


def test_conteggi_per_modalita(esempio: Questionnaire) -> None:
    versioni = adapt_all(esempio)
    assert len(versioni[Mode.CAWI].questions) == 10
    assert len(versioni[Mode.CATI].questions) == 12, "la griglia da 3 item diventa 3 domande"
    assert len(versioni[Mode.CAPI].questions) == 10
    for mq in versioni.values():
        assert mq.questionnaire_id == "mercato_v1"
        assert all(q.source_id in {qq.id for qq in esempio.questions} for q in mq.questions)


def test_cawi(esempio: Questionnaire) -> None:
    cawi = adapt(esempio, Mode.CAWI)
    q1 = cawi.question("q1")
    assert q1.dont_know_visible and not q1.read_options and not q1.show_card
    assert "Scala da 1 a 10" in q1.text
    q5 = cawi.question("q5")
    assert q5.type is QuestionType.GRID and q5.items is not None and len(q5.items) == 3
    assert cawi.pages == {
        1: ["q1"],
        2: ["q2", "q3"],
        3: ["q4"],
        4: ["q5"],
        5: ["q6", "q7"],
        6: ["q8", "q9"],
        7: ["q10"],
    }
    assert cawi.question("q6").text.endswith("(in euro)")


def test_cawi_pagine_implicite(esempio: Questionnaire) -> None:
    senza_pagine = esempio.model_copy(
        update={
            "sections": [
                s.model_copy(
                    update={"questions": [q.model_copy(update={"page": None}) for q in s.questions]}
                )
                for s in esempio.sections
            ]
        }
    )
    cawi = adapt(senza_pagine, Mode.CAWI)
    assert list(cawi.pages) == list(range(1, 11)), "una domanda per pagina"


def test_cati(esempio: Questionnaire) -> None:
    cati = adapt(esempio, Mode.CATI)
    ids = [q.id for q in cati.questions]
    assert ids[4:7] == ["q5.a", "q5.b", "q5.c"]
    primo, secondo = cati.question("q5.a"), cati.question("q5.b")
    assert primo.item_id == "a" and primo.source_id == "q5" and primo.type is QuestionType.SCALE
    assert "da 1 a 5" in primo.text and "Per niente d'accordo" in primo.text
    assert (
        "da 1 a 5" not in secondo.text
        and secondo.interviewer_note
        and "Ripetere" in secondo.interviewer_note
    )
    assert primo.show_if is None and not primo.dont_know_visible
    assert "non so" in (primo.interviewer_note or "").lower()
    q2 = cati.question("q2")
    assert q2.read_options and "Le leggo le possibili risposte" in q2.text
    assert q2.page is None and q2.show_if == "q1 <= 5"
    q1 = cati.question("q1")
    assert "dove 1 significa «Per nulla» e 10 significa «Del tutto»" in q1.text
    q10 = cati.question("q10")
    assert q10.interviewer_note and "sensibile" in q10.interviewer_note
    q4 = cati.question("q4")
    assert q4.interviewer_note and "al massimo 3" in q4.interviewer_note


def test_capi(esempio: Questionnaire) -> None:
    capi = adapt(esempio, Mode.CAPI)
    q1, q2, q4, q5 = (capi.question(i) for i in ("q1", "q2", "q4", "q5"))
    assert q1.show_card and "cartellino" in q1.text
    assert not q2.show_card and q2.read_options, "4 opzioni: lette, senza cartellino"
    assert q4.show_card and not q4.read_options, "6 opzioni: cartellino"
    assert q5.show_card and q5.items is not None and len(q5.items) == 3, (
        "griglia intera con cartellino"
    )
    assert (
        not q1.dont_know_visible and q1.interviewer_note and "non so" in q1.interviewer_note.lower()
    )


def test_ordine_opzioni(esempio: Questionnaire) -> None:
    cawi = adapt(esempio, Mode.CAWI)
    q2 = cawi.question("q2")
    base = option_order(q2, None, randomize=True)
    assert base == [
        "Prezzo",
        "Servizio clienti",
        "Trasparenza della bolletta",
        "Altro",
        DONT_KNOW_LABEL,
    ]
    rnd = option_order(q2, np.random.default_rng(3), randomize=True)
    assert rnd[-2:] == ["Altro", DONT_KNOW_LABEL]
    assert sorted(rnd[:3]) == sorted(base[:3])
    assert option_order(q2, np.random.default_rng(3), randomize=True) == rnd, "riproducibile"
    assert option_order(q2, np.random.default_rng(3), randomize=False) == base, "config disattiva"
    q3 = cawi.question("q3")
    assert option_order(q3, np.random.default_rng(1), randomize=True)[:3] == q3.options, (
        "non randomizzabile"
    )
    cati_q2 = adapt(esempio, Mode.CATI).question("q2")
    assert DONT_KNOW_LABEL not in option_order(cati_q2, None, randomize=False)


def test_esportazione(esempio: Questionnaire, tmp_path: Path) -> None:
    for mode in Mode:
        mq = adapt(esempio, mode)
        hashes = export(mq, tmp_path)
        assert set(hashes) == {f"mercato_v1_{mode.value}.yaml", f"mercato_v1_{mode.value}.md"}
        data = yaml.safe_load(
            (tmp_path / f"mercato_v1_{mode.value}.yaml").read_text(encoding="utf-8")
        )
        assert data["mode"] == mode.value and len(data["questions"]) == len(mq.questions)
        assert data["questions"][0]["scale"]["max"] == 10
        md = (tmp_path / f"mercato_v1_{mode.value}.md").read_text(encoding="utf-8")
        assert md.startswith("# mercato_v1 v1.1")
        assert to_markdown(mq) == md and to_yaml(mq) == (
            tmp_path / f"mercato_v1_{mode.value}.yaml"
        ).read_text(encoding="utf-8")
    cawi_md = (tmp_path / "mercato_v1_cawi.md").read_text(encoding="utf-8")
    assert "## Pagina 2" in cawi_md and DONT_KNOW_LABEL in cawi_md
    cati_md = (tmp_path / "mercato_v1_cati.md").read_text(encoding="utf-8")
    assert (
        "### q5.a" in cati_md and "> Intervistatore:" in cati_md and DONT_KNOW_LABEL not in cati_md
    )
    capi_md = (tmp_path / "mercato_v1_capi.md").read_text(encoding="utf-8")
    assert "**Cartellino**" in capi_md


def test_cli_validate_ed_export(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "questionnaire",
            "validate",
            str(ESEMPIO),
            "--config",
            str(ESEMPI_DIR / "mercato_100.yaml"),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "Questionario valido" in res.output and "cati: 12 domande" in res.output
    rotto = tmp_path / "rotto.yaml"
    rotto.write_text("id: x\nsections: []\n", encoding="utf-8")
    res = runner.invoke(app, ["questionnaire", "validate", str(rotto)])
    assert res.exit_code == 1 and "non valido" in res.output
    res = runner.invoke(
        app,
        ["questionnaire", "export", str(ESEMPIO), "--out", str(tmp_path / "out"), "--mode", "cati"],
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / "out" / "mercato_v1_cati.md").is_file()
    assert not (tmp_path / "out" / "mercato_v1_cawi.md").exists()
    res = runner.invoke(
        app, ["questionnaire", "export", str(ESEMPIO), "--out", str(tmp_path / "all")]
    )
    assert res.exit_code == 0 and len(list((tmp_path / "all").glob("*"))) == 6


def test_versione_cati_senza_dont_know(esempio: Questionnaire) -> None:
    with pytest.raises(KeyError):
        adapt(esempio, Mode.CATI).question("q5")


def test_rilancio_solo_a_voce(raw: dict[str, Any]) -> None:
    q7 = domanda(raw, "q7")
    q7["probe"] = "E l'energia, dove sta in questa lista?"
    q7["coding_note"] = "Energia citata: sì/no"
    q = parse_questionnaire(raw)
    cawi, cati, capi = (adapt(q, m) for m in (Mode.CAWI, Mode.CATI, Mode.CAPI))
    assert cawi.question("q7").probe is None, "senza interlocutore il rilancio non si applica"
    assert cawi.question("q7").coding_note == "Energia citata: sì/no"
    assert cati.question("q7").probe == "E l'energia, dove sta in questa lista?"
    assert capi.question("q7").probe == "E l'energia, dove sta in questa lista?"
    assert cati.question("q1").probe is None
    md = to_markdown(cati)
    assert "> Rilancio (una sola volta, dopo la risposta spontanea): «E l'energia" in md
    assert "> Per l'analisi: Energia citata: sì/no" in md
    assert "Rilancio" not in to_markdown(cawi)
    esportato = yaml.safe_load(to_yaml(capi))
    per_id = {d["id"]: d for d in esportato["questions"]}
    assert per_id["q7"]["probe"] == "E l'energia, dove sta in questa lista?"
    assert per_id["q1"]["probe"] is None
