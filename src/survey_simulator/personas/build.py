"""Costruzione delle persone a partire dal campione di M3."""

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from survey_simulator.config.schema import SurveySimulatorConfig
from survey_simulator.personas.attributes import AttributeSampler, _age_band
from survey_simulator.personas.coherence import hard_violations, sample_warnings
from survey_simulator.personas.narrative import render_narrative, template_hash
from survey_simulator.personas.schema import (
    PRIORS_DIR,
    Attitudes,
    Firm,
    Names,
    Persona,
    Priors,
    Provenance,
    ResponseStyle,
    load_names,
    load_priors,
)
from survey_simulator.population.istat.manifest import read_manifest
from survey_simulator.population.sample import SampleResult
from survey_simulator.population.tables import IstatTables

PERSONAS_SEED_BRANCH = 4  # ramo del seed di progetto riservato alle persone

TRAITS = ("sensibilita_prezzo", "fedelta_marca", "propensione_rischio", "apertura_novita")
STYLES = ("acquiescenza", "desiderabilita_sociale", "non_so", "tempo_disponibile", "loquacita")
AVQ = ("trust", "life_satisfaction", "internet", "political_info", "religion")


@dataclass(frozen=True)
class PersonasResult:
    personas: list[Persona]
    frame: pl.DataFrame
    warnings: list[str]
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _source_versions(processed_dir: Path | None, priors_path: Path | None) -> dict[str, str]:
    versions: dict[str, str] = {"template": template_hash()}
    file = priors_path if priors_path is not None else PRIORS_DIR / "default.yaml"
    versions["priors"] = hashlib.sha256(file.read_bytes()).hexdigest()
    if processed_dir is not None:
        manifest = read_manifest(processed_dir)
        if manifest is not None:
            for name, entry in manifest.tables.items():
                versions[name] = entry.sha256
    return versions


def _is_firm(unit: dict[str, Any]) -> bool:
    kind = unit.get("unit_kind")
    if kind:
        return str(kind) == "imprese"
    return str(unit["source"]) == "istat_imprese"


def _assemble(
    unit: dict[str, Any],
    attrs: dict[str, Any],
    prov: dict[str, Provenance],
    index: int,
    name: str | None,
    versions: dict[str, str],
) -> Persona:
    firm = None
    if _is_firm(unit):
        firm = Firm(
            sector=unit["sector"],
            size_class=unit["size_class"],
            employees=attrs["employees"],
            respondent_role=attrs["respondent_role"],
            with_relations=attrs["with_relations"],
            objectives=attrs["objectives"],
        )
        sex, age = attrs["sex"], attrs["age"]
        education, employment = attrs["education"], attrs["employment"]
    else:
        sex, age = unit["sex"], int(unit["age"])
        education, employment = unit["education"], unit["employment"]
    persona = Persona(
        persona_id=f"p_{index + 1:05d}",
        unit_id=unit["unit_id"],
        segment=unit["segment"],
        source=unit["source"],
        region=unit["region"],
        macro_area=unit["macro_area"],
        sex=sex,
        age=age,
        age_band=_age_band(age),
        education=education,
        employment=employment,
        income_quintile=attrs["income_quintile"],
        economic_judgement=attrs["economic_judgement"],
        firm=firm,
        attitudes=Attitudes(**{k: attrs[k] for k in (*AVQ, *TRAITS)}),
        response_style=ResponseStyle(**{k: attrs[k] for k in STYLES}),
        name=name,
        provenance=prov,
        source_versions=versions,
        weight=float(unit["weight"]),
        weight_pop=float(unit["weight_pop"]),
    )
    return persona.model_copy(update={"narrative": render_narrative(persona)})


def build_personas(
    sample: SampleResult,
    config: SurveySimulatorConfig,
    tables: IstatTables,
    *,
    processed_dir: Path | None = None,
    priors: Priors | None = None,
    names: Names | None = None,
) -> PersonasResult:
    """Una persona per unità del campione, deterministica dal seed di progetto.

    Il generatore deriva da `SeedSequence([seed, 4])`, indipendente da quello
    del campione: cambiare i priori non cambia il campione e viceversa.
    """
    priors = priors if priors is not None else load_priors(config.personas.priors_path)
    if names is None and config.personas.include_names:
        names = load_names()
    sampler = AttributeSampler(tables, priors, names if config.personas.include_names else None)
    versions = _source_versions(processed_dir, config.personas.priors_path)
    allowed_roles = {name: seg.respondent_role for name, seg in config.sample.segments.items()}
    units = sample.units.to_dicts()
    seeds = np.random.SeedSequence([config.project.seed, PERSONAS_SEED_BRANCH]).spawn(len(units))
    personas: list[Persona] = []
    warnings: list[str] = []
    tentativi: Counter[str] = Counter()
    avvisi_campione: Counter[str] = Counter()
    for i, (unit, seed) in enumerate(zip(units, seeds, strict=True)):
        rng = np.random.default_rng(seed)
        for w in sample_warnings(unit):
            avvisi_campione[w] += 1
        attrs: dict[str, Any] = {}
        prov: dict[str, Provenance] = {}
        for _attempt in range(1, priors.coherence.max_attempts + 1):
            if _is_firm(unit):
                attrs, prov = sampler.firm(unit, allowed_roles.get(unit["segment"]), rng)
            else:
                attrs, prov = sampler.individual(unit, rng)
            violazioni = hard_violations({**unit, **attrs})
            if not violazioni:
                break
            tentativi[violazioni[0]] += 1
        else:
            warnings.append(
                f"{unit['unit_id']}: coerenza non raggiunta dopo {priors.coherence.max_attempts} "
                f"tentativi ({'; '.join(violazioni)})"
            )
        sex = str(attrs.get("sex", unit.get("sex")))
        age = int(attrs.get("age", unit.get("age") or 0))
        name = sampler.name_for(sex, age, rng) if names is not None else None
        personas.append(_assemble(unit, attrs, prov, i, name, versions))
    for w, n in avvisi_campione.items():
        warnings.append(f"{n} persone dal campione con combinazione rara: {w}")
    frame = personas_frame(personas)
    diagnostics = {
        "n": len(personas),
        "riestrazioni": dict(tentativi),
        "combinazioni_rare_dal_campione": dict(avvisi_campione),
        "provenienze": dict(
            Counter(p for persona in personas for p in persona.provenance.values())
        ),
    }
    return PersonasResult(
        personas=personas, frame=frame, warnings=warnings, diagnostics=diagnostics
    )


def personas_frame(personas: list[Persona]) -> pl.DataFrame:
    """Tabella piatta: una riga per persona, attributi annidati con prefisso."""
    rows: list[dict[str, Any]] = []
    for p in personas:
        row: dict[str, Any] = {
            "persona_id": p.persona_id,
            "unit_id": p.unit_id,
            "segment": p.segment,
            "source": p.source,
            "name": p.name,
            "region": p.region,
            "macro_area": p.macro_area,
            "sex": p.sex,
            "age": p.age,
            "age_band": p.age_band,
            "education": p.education,
            "employment": p.employment,
            "income_quintile": p.income_quintile,
            "economic_judgement": p.economic_judgement,
            "sector": p.firm.sector if p.firm else None,
            "size_class": p.firm.size_class if p.firm else None,
            "employees": p.firm.employees if p.firm else None,
            "respondent_role": p.firm.respondent_role if p.firm else None,
            "with_relations": p.firm.with_relations if p.firm else None,
            "objectives": ";".join(p.firm.objectives) if p.firm else None,
        }
        row.update(p.attitudes.model_dump())
        row.update({f"style_{k}": v for k, v in p.response_style.model_dump().items()})
        row["weight"] = p.weight
        row["weight_pop"] = p.weight_pop
        row["narrative"] = p.narrative
        rows.append(row)
    # Schema inferito su tutte le righe: le colonne d'impresa sono nulle per i consumer.
    return pl.DataFrame(rows, infer_schema_length=None)


def personas_markdown(personas: list[Persona]) -> str:
    """Documento di revisione: profilo strutturato e narrativa per ogni persona."""
    parti = ["# Persone generate\n"]
    for p in personas:
        parti.append(f"## {p.persona_id} ({p.segment}, {p.unit_id})\n")
        campi = [
            f"regione: {p.region}",
            f"sesso: {p.sex}",
            f"età: {p.age}",
            f"istruzione: {p.education}",
            f"condizione: {p.employment}",
            f"quintile di reddito: {p.income_quintile}",
            f"giudizio economico: {p.economic_judgement}",
        ]
        if p.firm:
            campi += [
                f"settore: {p.firm.sector}",
                f"classe: {p.firm.size_class} ({p.firm.employees} addetti)",
                f"ruolo: {p.firm.respondent_role}",
                f"relazioni: {'sì' if p.firm.with_relations else 'no'}",
                f"obiettivi: {', '.join(p.firm.objectives) or 'nessuno'}",
            ]
        a = p.attitudes
        campi += [
            f"fiducia: {a.trust}",
            f"soddisfazione: {a.life_satisfaction}",
            f"internet: {a.internet}",
            f"politica: {a.political_info}",
            f"religione: {a.religion}",
            "tratti (ipotesi): " + ", ".join(f"{k}={getattr(a, k):.2f}" for k in TRAITS),
            "stile (ipotesi): "
            + ", ".join(f"{k}={getattr(p.response_style, k):.2f}" for k in STYLES),
        ]
        parti.append("- " + "\n- ".join(campi) + "\n")
        parti.append(f"> {p.narrative}\n")
    return "\n".join(parti)
