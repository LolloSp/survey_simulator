"""Controlli incrociati sulla configurazione e stime preliminari.

Ogni regola è una funzione `(config) -> list[Issue]`; il loader le applica
tutte dopo la validazione dello schema e raccoglie errori e avvisi insieme,
così chi scrive la configurazione vede tutti i problemi in una volta sola.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import floor

from survey_simulator.config.schema import (
    LISTA_CLIENTI,
    Allocation,
    Design,
    SegmentConfig,
    SurveySimulatorConfig,
)
from survey_simulator.config.sources import SOURCES, CategoricalFilter, DataSource, RangeFilter

MIN_CASI_PER_CELLA = 3


class Level(StrEnum):
    ERROR = "errore"
    WARNING = "avviso"


@dataclass(frozen=True)
class Issue:
    level: Level
    location: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.location}: {self.message}"


def _err(location: str, message: str) -> Issue:
    return Issue(Level.ERROR, location, message)


def _warn(location: str, message: str) -> Issue:
    return Issue(Level.WARNING, location, message)


# --------------------------------------------------------------------------- #
# Dimensioni dei segmenti
# --------------------------------------------------------------------------- #


def segment_sizes(config: SurveySimulatorConfig) -> dict[str, int]:
    """Numero di persone per segmento, derivato da `size` o da `share` per `total`.

    Con `share`, gli arrotondamenti vengono compensati sul segmento più grande
    in modo che la somma coincida con `total`. Con allocazione `proportional`
    le dimensioni arrivano dai dati di popolazione (M3): qui si usa una
    ripartizione uniforme come segnaposto.
    """
    sample = config.sample
    nomi = list(sample.segments)
    if sample.total is None:
        # Anagrafiche: la dimensione è nota solo leggendo il file; size se indicata.
        return {n: (s.size or 0) for n, s in sample.segments.items()}
    if sample.allocation is Allocation.PROPORTIONAL:
        base = sample.total // len(nomi)
        sizes = dict.fromkeys(nomi, base)
        sizes[nomi[0]] += sample.total - base * len(nomi)
        return sizes

    if all(s.size is not None for s in sample.segments.values()):
        return {n: s.size for n, s in sample.segments.items() if s.size is not None}

    sizes = {n: round((s.share or 0.0) * sample.total) for n, s in sample.segments.items()}
    scarto = sample.total - sum(sizes.values())
    if scarto:
        piu_grande = max(sizes, key=lambda n: sizes[n])
        sizes[piu_grande] += scarto
    return sizes


# --------------------------------------------------------------------------- #
# Regole
# --------------------------------------------------------------------------- #

Rule = Callable[[SurveySimulatorConfig], list[Issue]]


def is_contacts_config(config: SurveySimulatorConfig) -> bool:
    """Vero se il campione viene da anagrafiche (tutti i segmenti lista_clienti)."""
    return all(s.source == LISTA_CLIENTI for s in config.sample.segments.values())


def rule_contacts_consistency(config: SurveySimulatorConfig) -> list[Issue]:
    """Anagrafiche e sorgenti ISTAT non si mescolano; con le anagrafiche total resta null."""
    segs = config.sample.segments
    liste = [n for n, s in segs.items() if s.source == LISTA_CLIENTI]
    if not liste:
        if config.sample.total is None:
            return [_err("sample.total", "obbligatorio con le sorgenti ISTAT")]
        return []
    issues: list[Issue] = []
    if len(liste) != len(segs):
        issues.append(
            _err(
                "sample.segments",
                "non mescolare lista_clienti con le sorgenti ISTAT: usare configurazioni separate",
            )
        )
    if config.sample.total is not None:
        issues.append(
            _warn(
                "sample.total",
                "ignorato con lista_clienti: il campione sono i record validi "
                "(usare size nel segmento per un sottocampione)",
            )
        )
    for n in liste:
        if segs[n].share is not None:
            issues.append(_err(f"sample.segments.{n}.share", "non ammessa con lista_clienti"))
        if segs[n].oversample:
            issues.append(_err(f"sample.segments.{n}.oversample", "non ammesso con lista_clienti"))
    return issues


def rule_segment_allocation(config: SurveySimulatorConfig) -> list[Issue]:
    """Quote che sommano a 1 oppure dimensioni che sommano al totale, senza mescolarle."""
    sample = config.sample
    segs = sample.segments
    if is_contacts_config(config) or sample.total is None:
        return []
    con_share = [n for n, s in segs.items() if s.share is not None]
    con_size = [n for n, s in segs.items() if s.size is not None]
    doppi = [n for n, s in segs.items() if s.share is not None and s.size is not None]
    senza = [n for n, s in segs.items() if s.share is None and s.size is None]

    if sample.allocation is Allocation.PROPORTIONAL:
        if con_share or con_size:
            return [
                _warn(
                    "sample.segments",
                    "con allocation=proportional share e size sono ignorati: le dimensioni "
                    "dei segmenti derivano dalla popolazione (M3)",
                )
            ]
        return []

    issues: list[Issue] = []
    for n in doppi:
        issues.append(_err(f"sample.segments.{n}", "indicare share oppure size, non entrambi"))
    for n in senza:
        issues.append(_err(f"sample.segments.{n}", "indicare share oppure size"))
    if issues:
        return issues

    if con_share and con_size:
        return [
            _err(
                "sample.segments",
                f"non mescolare share ({', '.join(con_share)}) e size ({', '.join(con_size)}): "
                "usare la stessa forma per tutti i segmenti",
            )
        ]
    if con_share:
        totale = sum(s.share or 0.0 for s in segs.values())
        if abs(totale - 1.0) > 1e-6:
            issues.append(
                _err("sample.segments", f"le share dei segmenti sommano a {totale:.4f}, non a 1")
            )
    else:
        totale_size = sum(s.size or 0 for s in segs.values())
        if totale_size != sample.total:
            issues.append(
                _err(
                    "sample.segments",
                    f"le size dei segmenti sommano a {totale_size}, "
                    f"non a sample.total={sample.total}",
                )
            )
    return issues


def _check_segment_against_source(name: str, seg: SegmentConfig, source: DataSource) -> list[Issue]:
    loc = f"sample.segments.{name}"
    issues: list[Issue] = []

    sconosciute = [q for q in seg.quotas if q not in source.quota_variables]
    if sconosciute:
        issues.append(
            _err(
                f"{loc}.quotas",
                f"variabili non disponibili in {source.name}: {', '.join(sconosciute)}; "
                f"ammesse: {', '.join(source.quota_variables)}",
            )
        )

    for variabile, proporzioni in seg.oversample.items():
        qv = source.quota_variables.get(variabile)
        if qv is None:
            issues.append(
                _err(
                    f"{loc}.oversample.{variabile}",
                    f"variabile non disponibile in {source.name}; "
                    f"ammesse: {', '.join(source.quota_variables)}",
                )
            )
            continue
        ignote = [c for c in proporzioni if c not in qv.categories]
        if ignote:
            issues.append(
                _err(
                    f"{loc}.oversample.{variabile}",
                    f"categorie sconosciute: {', '.join(ignote)}; "
                    f"ammesse: {', '.join(qv.categories)}",
                )
            )

    for nome_filtro, valore in seg.filters.items():
        spec = source.filters.get(nome_filtro)
        floc = f"{loc}.filters.{nome_filtro}"
        if spec is None:
            issues.append(
                _err(
                    floc,
                    f"filtro non disponibile in {source.name}; "
                    f"ammessi: {', '.join(source.filters)}",
                )
            )
            continue
        if isinstance(spec, RangeFilter):
            if not isinstance(valore, tuple):
                issues.append(_err(floc, "atteso un intervallo [min, max]"))
                continue
            lo, hi = valore
            if lo > hi:
                issues.append(_err(floc, f"intervallo invertito: {lo} > {hi}"))
            if lo < spec.min_allowed or hi > spec.max_allowed:
                issues.append(
                    _err(
                        floc,
                        f"intervallo [{lo}, {hi}] fuori dai limiti plausibili "
                        f"[{spec.min_allowed}, {spec.max_allowed}]",
                    )
                )
        elif isinstance(spec, CategoricalFilter):
            if valore == "all":
                continue
            if not isinstance(valore, list):
                issues.append(_err(floc, 'attesa una lista di categorie oppure "all"'))
                continue
            ignote = [c for c in valore if c not in spec.categories]
            if ignote:
                issues.append(
                    _err(
                        floc,
                        f"categorie sconosciute: {', '.join(ignote)}; "
                        f"ammesse: {', '.join(spec.categories)}",
                    )
                )

    if seg.respondent_role is not None:
        if source.unit != "imprese" and not source.respondent_roles:
            issues.append(
                _err(f"{loc}.respondent_role", "ammesso solo per segmenti con sorgente imprese")
            )
        else:
            ignoti = [r for r in seg.respondent_role if r not in source.respondent_roles]
            if ignoti:
                issues.append(
                    _err(
                        f"{loc}.respondent_role",
                        f"ruoli sconosciuti: {', '.join(ignoti)}; "
                        f"ammessi: {', '.join(source.respondent_roles)}",
                    )
                )
    return issues


def rule_segments_match_sources(config: SurveySimulatorConfig) -> list[Issue]:
    """Sorgente esistente; quote, filtri, oversample e ruoli coerenti con la sorgente."""
    issues: list[Issue] = []
    for name, seg in config.sample.segments.items():
        source = SOURCES.get(seg.source)
        if source is None:
            issues.append(
                _err(
                    f"sample.segments.{name}.source",
                    f"sorgente '{seg.source}' sconosciuta; "
                    f"disponibili: {', '.join(sorted(SOURCES))}",
                )
            )
            continue
        issues.extend(_check_segment_against_source(name, seg, source))
    return issues


def _intersecano(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def rule_impossible_combinations(config: SurveySimulatorConfig) -> list[Issue]:
    """Combinazioni che nessuna persona reale può soddisfare.

    Oggi: sovracampionare una classe dimensionale di impresa esclusa dal filtro
    sugli addetti. Nuove regole si aggiungono qui.
    """
    issues: list[Issue] = []
    for name, seg in config.sample.segments.items():
        source = SOURCES.get(seg.source)
        if source is None or not source.size_class_bounds:
            continue
        addetti = seg.filters.get("employees")
        proporzioni = seg.oversample.get("size_class")
        if not isinstance(addetti, tuple) or not proporzioni:
            continue
        lo, hi = addetti
        escluse = [
            classe
            for classe, quota in proporzioni.items()
            if quota > 0
            and classe in source.size_class_bounds
            and not _intersecano(source.size_class_bounds[classe], (lo, hi))
        ]
        if escluse:
            issues.append(
                _err(
                    f"sample.segments.{name}.oversample.size_class",
                    f"le classi {', '.join(escluse)} sono escluse dal filtro "
                    f"employees=[{lo}, {hi}]: combinazione impossibile",
                )
            )
    return issues


def rule_small_cells(config: SurveySimulatorConfig) -> list[Issue]:
    """Avviso se una variabile di quota avrebbe meno di 3 casi attesi per categoria.

    Stima con categorie uniformi (dimensione del segmento / numero di categorie);
    in M3 viene sostituita dai marginali ISTAT reali.
    """
    issues: list[Issue] = []
    sizes = segment_sizes(config)
    for name, seg in config.sample.segments.items():
        source = SOURCES.get(seg.source)
        if source is None:
            continue
        n = sizes[name]
        for q in seg.quotas:
            qv = source.quota_variables.get(q)
            if qv is None:
                continue
            k = len(qv.categories)
            attesi = n / k
            if attesi < MIN_CASI_PER_CELLA:
                max_categorie = max(1, floor(n / MIN_CASI_PER_CELLA))
                issues.append(
                    _warn(
                        f"sample.segments.{name}.quotas.{q}",
                        f"circa {attesi:.1f} casi attesi per categoria ({n} persone su {k} "
                        f"categorie): accorpare le categorie di {q} fino a un massimo di "
                        f"{max_categorie}",
                    )
                )
    return issues


def rule_modes_allocation_unused(config: SurveySimulatorConfig) -> list[Issue]:
    """In within_subject l'allocazione per modalità non ha effetto."""
    if config.modes.design is Design.WITHIN_SUBJECT and config.modes.allocation is not None:
        return [
            _warn(
                "modes.allocation",
                "ignorata con design within_subject: ogni persona risponde in tutte le modalità",
            )
        ]
    return []


def rule_temperature_unsupported(config: SurveySimulatorConfig) -> list[Issue]:
    """I modelli Claude attuali rifiutano `temperature`: l'adapter la ignora."""
    if config.engine.temperature is None:
        return []
    anthropic = [m.model for m in config.engine.models if m.provider == "anthropic"]
    if not anthropic:
        return []
    return [
        _warn(
            "engine.temperature",
            f"ignorata dal provider anthropic ({', '.join(anthropic)}): i modelli Claude "
            "attuali non accettano il parametro; la variabilità fra repliche viene dal "
            "modello e da engine.effort",
        )
    ]


def rule_pilot_size(config: SurveySimulatorConfig) -> list[Issue]:
    """Il pilota non può essere più grande del campione."""
    if config.sample.total is not None and config.run.pilot_size > config.sample.total:
        return [
            _err(
                "run.pilot_size",
                f"{config.run.pilot_size} supera sample.total={config.sample.total}",
            )
        ]
    return []


RULES: tuple[Rule, ...] = (
    rule_contacts_consistency,
    rule_segment_allocation,
    rule_segments_match_sources,
    rule_impossible_combinations,
    rule_small_cells,
    rule_modes_allocation_unused,
    rule_temperature_unsupported,
    rule_pilot_size,
)


def apply_rules(config: SurveySimulatorConfig, rules: tuple[Rule, ...] = RULES) -> list[Issue]:
    issues: list[Issue] = []
    for rule in rules:
        issues.extend(rule(config))
    return issues


# --------------------------------------------------------------------------- #
# Stima del volume
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InterviewEstimate:
    personas: int
    modes_per_persona: int
    replicates: int
    models: int

    @property
    def interviews(self) -> int:
        return self.personas * self.modes_per_persona * self.replicates * self.models


def estimate_interviews(config: SurveySimulatorConfig) -> InterviewEstimate:
    """Numero di interviste che il run eseguirà.

    La stima in euro richiede i prezzi dei modelli e la lunghezza del
    questionario: arriva con il livello LLM (M6) e il runner (M9).
    """
    totale = config.sample.total
    if totale is None:
        totale = sum(segment_sizes(config).values())  # 0 se le anagrafiche non hanno size
    personas = config.run.pilot_size if config.run.pilot else totale
    modes = len(config.modes.enabled) if config.modes.design is Design.WITHIN_SUBJECT else 1
    return InterviewEstimate(
        personas=personas,
        modes_per_persona=modes,
        replicates=config.engine.replicates,
        models=len(config.engine.models),
    )
