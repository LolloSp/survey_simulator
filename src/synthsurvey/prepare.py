"""`synthsurvey prepare`: da questionario e anagrafica alla configurazione pronta (M13).

Passi:

1. profila l'anagrafica (colonne riconosciute, record validi, scarti) e
   decide i segmenti: `privati` per gli individui, `imprese` per le imprese;
2. prende il questionario: YAML già strutturato oppure Word/PDF/Excel da
   importare con l'agente (M6b), nel qual caso scrive anche il rapporto;
3. scrive `config.yaml` con default prudenti (tre modalità, tre repliche,
   budget basso) e stima costo e volume senza chiamate.

Tutto finisce nella cartella indicata; la sessione di Claude Code (skill
`synthsurvey-run`) la usa per mostrare il riepilogo e lanciare il run.
"""

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from synthsurvey.config import ConfigError, load_config
from synthsurvey.population.contacts import ContactsError, ContactsResult, load_contacts

DEFAULT_MODEL = {"provider": "anthropic", "model": "claude-opus-5-5"}
QUESTIONNAIRE_YAML = (".yaml", ".yml")
SEGMENT_NAMES = {"individui": "privati", "imprese": "imprese"}


class PrepareError(Exception):
    """Preparazione interrotta: anagrafica, questionario o configurazione non utilizzabili."""


@dataclass
class PrepareResult:
    out_dir: Path
    config_path: Path
    questionnaire_path: Path
    contacts: ContactsResult
    segments: dict[str, int]
    import_report: Path | None = None
    questionnaire_imported: bool = False
    estimate: Any = None  # CostEstimate del runner, se calcolata
    warnings: list[str] = field(default_factory=list)


def draft_config(
    *,
    project_name: str,
    contacts_path: Path,
    questionnaire_path: Path,
    out_dir: Path,
    contacts: ContactsResult,
    model: dict[str, str],
    modes: list[str],
    replicates: int,
    budget_eur: float,
    seed: int,
    sheet: str | None,
    mapping: dict[str, str] | None,
    size: int | None = None,
) -> dict[str, Any]:
    """Configurazione di progetto con un segmento per unità presente nell'anagrafica."""
    per_unit = contacts.report()["by_unit"]
    segments: dict[str, Any] = {}
    for unit, nome in SEGMENT_NAMES.items():
        if per_unit.get(unit, 0) == 0:
            continue
        blocco: dict[str, Any] = {
            "source": "lista_clienti",
            "contacts": {"path": _relativo(contacts_path, out_dir), "unit": unit},
        }
        if sheet:
            blocco["contacts"]["sheet"] = sheet
        if mapping:
            blocco["contacts"]["mapping"] = dict(mapping)
        if size is not None:
            blocco["size"] = size
        if unit == "imprese":
            blocco["respondent_role"] = ["titolare", "amministratore", "responsabile_acquisti"]
        segments[nome] = blocco
    if not segments:
        raise PrepareError("nessun record utilizzabile nell'anagrafica")
    return {
        "project": {"name": project_name, "seed": seed},
        "sample": {"total": None, "segments": segments},
        "questionnaire": {"path": _relativo(questionnaire_path, out_dir)},
        "personas": {"include_names": True},
        "modes": {"design": "within_subject", "enabled": modes},
        "engine": {
            "models": [dict(model)],
            "effort": "low",
            "max_tokens": 1024,
            "concurrency": 4,
            "replicates": replicates,
            "nonverbal": {"enabled": True},
        },
        "run": {"pilot": False, "pilot_size": 12, "frozen": False, "budget_max_eur": budget_eur},
        "output": {"formats": ["parquet", "csv", "sav"], "dir": "runs"},
    }


def _relativo(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _slug(text: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "progetto"


def prepare(
    *,
    questionnaire: Path,
    contacts_path: Path,
    out_dir: Path,
    project_name: str | None = None,
    model: dict[str, str] | None = None,
    modes: list[str] | None = None,
    replicates: int = 3,
    budget_eur: float = 50.0,
    seed: int = 20261108,
    sheet: str | None = None,
    mapping: dict[str, str] | None = None,
    data_dir: Path = Path("data"),
    estimate: bool = True,
    import_rounds: int = 2,
    size: int | None = None,
) -> PrepareResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    nome = project_name or _slug(questionnaire.stem)
    modello = model or DEFAULT_MODEL
    modalita = modes or ["cawi", "cati", "capi"]
    try:
        contacts = load_contacts(contacts_path, sheet=sheet, mapping=mapping)
    except ContactsError as exc:
        raise PrepareError(f"anagrafica: {exc}") from exc
    if contacts.n == 0:
        raise PrepareError("anagrafica: nessun record utilizzabile")
    avvisi: list[str] = []

    # Questionario: YAML pronto oppure da importare.
    q_dest = out_dir / "questionnaire.yaml"
    importato = False
    rapporto: Path | None = None
    if questionnaire.suffix.lower() in QUESTIONNAIRE_YAML:
        if questionnaire.resolve() != q_dest.resolve():
            shutil.copyfile(questionnaire, q_dest)
    else:
        importato = True
        q_dest.write_text("id: segnaposto\nsections: []\n", encoding="utf-8")

    raw = draft_config(
        project_name=nome,
        contacts_path=contacts_path,
        questionnaire_path=q_dest,
        out_dir=out_dir,
        contacts=contacts,
        model=modello,
        modes=modalita,
        replicates=replicates,
        budget_eur=budget_eur,
        seed=seed,
        sheet=sheet,
        mapping=mapping,
        size=size,
    )
    config_path = out_dir / "config.yaml"
    _write_config(config_path, raw)

    if importato:
        rapporto = _import_questionnaire(questionnaire, q_dest, config_path, import_rounds)

    try:
        loaded = load_config(config_path)
    except ConfigError as exc:
        raise PrepareError(str(exc)) from exc
    avvisi.extend(f"{w.location}: {w.message}" for w in loaded.warnings)
    from synthsurvey.questionnaire import QuestionnaireError, load_questionnaire

    try:
        caricato = load_questionnaire(q_dest, loaded.config)
    except QuestionnaireError as exc:
        raise PrepareError(
            f"{exc}; i segmenti di questo progetto sono: "
            f"{', '.join(raw['sample']['segments'])}. "
            "Allineare applies_to nel questionario o indicare uno YAML già coerente."
        ) from exc
    avvisi.extend(f"questionario: {w}" for w in caricato.warnings)
    per_unit = contacts.report()["by_unit"]
    segmenti = {
        nome: int(per_unit[unit]) for unit, nome in SEGMENT_NAMES.items() if unit in per_unit
    }
    result = PrepareResult(
        out_dir=out_dir,
        config_path=config_path,
        questionnaire_path=q_dest,
        contacts=contacts,
        segments=segmenti,
        import_report=rapporto,
        questionnaire_imported=importato,
        warnings=avvisi,
    )
    if estimate:
        from synthsurvey.runner import BudgetError, execute_run

        try:
            result.estimate = execute_run(loaded, data_dir=data_dir, estimate_only=True).estimate
        except BudgetError as exc:
            avvisi.append(f"budget: {exc}")
    # Rapporto dell'anagrafica, senza dati personali.
    (out_dir / "contacts_report.json").write_text(
        yaml.safe_dump(contacts.report(), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return result


def _write_config(path: Path, raw: dict[str, Any]) -> None:
    testa = (
        "# Configurazione generata da `synthsurvey prepare`: rivedere budget, modalità e\n"
        "# repliche prima del run. Il campione è l'anagrafica indicata nei segmenti.\n"
    )
    path.write_text(
        testa + yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _import_questionnaire(source: Path, dest: Path, config_path: Path, rounds: int) -> Path | None:
    from synthsurvey.llm import AwaitingAnswersError, make_pool
    from synthsurvey.questionnaire import (
        ExtractionError,
        extract_text,
        import_questionnaire,
        render_report,
        to_source_yaml,
    )

    loaded = load_config(config_path)
    try:
        doc = extract_text(source)
    except ExtractionError as exc:
        raise PrepareError(f"questionario: {exc}") from exc
    pool = make_pool(loaded.config.engine.models[0], loaded.config, use_cache=True)
    try:
        result = asyncio.run(
            import_questionnaire(doc, pool, config=loaded.config, max_rounds=rounds)
        )
    except AwaitingAnswersError as exc:
        raise PrepareError(
            "questionario: il provider sessione aspetta la trascrizione "
            f"({exc.path.name}); rispondere con `synthsurvey session answer` usando "
            f"--config {config_path} e rilanciare prepare con gli stessi argomenti"
        ) from exc
    rapporto = dest.with_suffix(".import.md")
    if result.raw is None:
        rapporto.write_text(render_report(result), encoding="utf-8")
        raise PrepareError(
            f"questionario: l'agente non ha prodotto una bozza utilizzabile (vedi {rapporto})"
        )
    dest.write_text(to_source_yaml(result.raw, result), encoding="utf-8")
    rapporto.write_text(render_report(result, yaml_path=dest), encoding="utf-8")
    if not result.valid:
        raise PrepareError(
            f"questionario importato ma non valido: correggere {dest} seguendo {rapporto}, "
            "poi rilanciare prepare indicando lo YAML corretto"
        )
    return rapporto


def summary_text(result: PrepareResult) -> str:
    from synthsurvey.population.contacts import profile_text

    righe = [profile_text(result.contacts), ""]
    righe.append("Segmenti: " + ", ".join(f"{k}={v}" for k, v in result.segments.items()))
    righe.append(f"Configurazione: {result.config_path}")
    righe.append(
        f"Questionario: {result.questionnaire_path}"
        + (" (importato dall'agente, da revisionare)" if result.questionnaire_imported else "")
    )
    if result.import_report:
        righe.append(f"Rapporto di importazione: {result.import_report}")
    if result.estimate is not None:
        e = result.estimate
        righe.append(
            f"Stima: {e.interviews} interviste, circa {e.calls} chiamate, "
            f"{e.cost_eur:.2f} EUR su budget {e.budget_eur:.2f} EUR"
            + ("" if e.within_budget else " (OLTRE IL BUDGET)")
        )
    for w in result.warnings:
        righe.append(f"Avviso: {w}")
    righe.append("")
    righe.append("Prossimi passi:")
    righe.append(f"  uv run synthsurvey run --config {result.config_path} --pilot")
    righe.append(f"  uv run synthsurvey run --config {result.config_path}")
    return "\n".join(righe)
