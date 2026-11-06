"""Priori YAML e schema della persona."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from synthsurvey.personas import Names, Priors, load_names, load_priors
from synthsurvey.personas.schema import PRIORS_DIR, level3
from synthsurvey.population import categories as cat


def test_priori_di_default_validi(priors: Priors) -> None:
    assert priors.version == 1
    assert set(priors.traits) == {
        "sensibilita_prezzo",
        "fedelta_marca",
        "propensione_rischio",
        "apertura_novita",
    }
    assert set(priors.response_style) == {
        "acquiescenza",
        "desiderabilita_sociale",
        "non_so",
        "tempo_disponibile",
        "loquacita",
    }
    for classe in cat.SIZE_CLASSES_PMI:
        assert abs(sum(priors.respondent_roles[classe].values()) - 1) < 1e-9
    # I modificatori usano solo categorie esistenti.
    valide = {
        "age_band": set(cat.AGE_BANDS),
        "education": set(cat.EDUCATION),
        "employment": set(cat.EMPLOYMENT),
        "sex": set(cat.SEX),
        "income_quintile": {"1", "2", "3", "4", "5"},
        "economic_judgement": {"ottime", "adeguate", "scarse", "insufficienti"},
        "internet": {"quotidiano", "occasionale", "mai"},
        "religion": {"settimanale", "saltuaria", "mai"},
        "political_info": {"quotidiana", "settimanale", "saltuaria", "mai"},
    }
    for gruppo in (priors.traits, priors.response_style):
        for nome, prior in gruppo.items():
            for dim, mapping in prior.modifiers.items():
                assert dim in valide, (nome, dim)
                assert set(mapping) <= valide[dim], (nome, dim, set(mapping) - valide[dim])


def test_priori_personalizzati(tmp_path: Path) -> None:
    raw = yaml.safe_load((PRIORS_DIR / "default.yaml").read_text(encoding="utf-8"))
    raw["traits"]["sensibilita_prezzo"]["base"] = 0.9
    path = tmp_path / "priori.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert load_priors(path).traits["sensibilita_prezzo"].base == 0.9


@pytest.mark.parametrize(
    ("percorso", "valore"),
    [
        (("traits", "sensibilita_prezzo", "base"), 1.5),
        (("respondent_roles", "micro", "titolare"), 0.5),
        (("income", "employed_split", "indipendente"), 0.5),
        (("firm_response_style", "loquacita"), {"colore": {"rosso": 0.1}}),
    ],
)
def test_priori_non_validi(percorso: tuple[str, ...], valore: object) -> None:
    raw = yaml.safe_load((PRIORS_DIR / "default.yaml").read_text(encoding="utf-8"))
    nodo = raw
    for k in percorso[:-1]:
        nodo = nodo[k]
    nodo[percorso[-1]] = valore
    with pytest.raises(ValidationError):
        Priors.model_validate(raw)


def test_priori_tratto_mancante() -> None:
    raw = yaml.safe_load((PRIORS_DIR / "default.yaml").read_text(encoding="utf-8"))
    del raw["traits"]["fedelta_marca"]
    with pytest.raises(ValidationError, match="traits"):
        Priors.model_validate(raw)


def test_nomi(names: Names) -> None:
    assert names.decades == [1940, 1950, 1960, 1970, 1980, 1990, 2000]
    assert all(len(v) >= 10 for v in names.f.values())
    assert all(len(v) >= 10 for v in names.m.values())
    assert "Giulia" in names.f[2000]
    assert "Giuseppe" in names.m[1940]
    assert load_names() == names


def test_livelli() -> None:
    assert level3(0.1) == "basso"
    assert level3(0.5) == "medio"
    assert level3(0.9) == "alto"
