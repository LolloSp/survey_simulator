"""Assegnazione degli attributi delle persone oltre la demografia del campione.

Gli attributi con fonte ISTAT sono estratti dalla distribuzione condizionata
al profilo (sesso, classe d'età, titolo di studio; regione; settore e classe
di addetti). Le correlazioni fra atteggiamenti oltre la demografia non sono
modellate. Gli attributi senza fonte seguono i priori YAML (provenienza
"ipotesi"). Tutta la casualità passa dal generatore ricevuto.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from survey_simulator.personas.schema import BetaPrior, Names, Priors, Provenance
from survey_simulator.population import categories as cat
from survey_simulator.population.tables import IstatTables

Dist = tuple[list[str], np.ndarray]  # categorie e probabilità


class ProfileError(ValueError):
    """Profilo senza distribuzione condizionata disponibile."""


def avq_age_class(age: int, *, young: str) -> str:
    """Classe d'età AVQ di un adulto; `young` è l'etichetta della classe più giovane."""
    if age <= 24:
        return young
    if age <= 44:
        return "25_44"
    if age <= 64:
        return "45_64"
    return "65_plus"


def lfs_age_class(age: int) -> str:
    for lo, hi, label in (
        (18, 24, "15_24"),
        (25, 34, "25_34"),
        (35, 44, "35_44"),
        (45, 54, "45_54"),
        (55, 64, "55_64"),
    ):
        if lo <= age <= hi:
            return label
    return "65_89"


def _dist_by_keys(
    df: pl.DataFrame, keys: list[str], cat_col: str, value_col: str
) -> dict[tuple[str, ...], Dist]:
    out: dict[tuple[str, ...], Dist] = {}
    for key, sub in df.group_by(keys, maintain_order=True):
        cats = [str(c) for c in sub[cat_col].to_list()]
        vals = np.array(sub[value_col].to_list(), dtype=np.float64)
        tot = vals.sum()
        if tot <= 0:
            continue
        out[tuple(str(k) for k in key)] = (cats, vals / tot)
    return out


@dataclass
class AttributeSampler:
    tables: IstatTables
    priors: Priors
    names: Names | None = None
    _avq: dict[str, dict[tuple[str, ...], Dist]] = field(init=False, default_factory=dict)
    _young: dict[str, str] = field(init=False, default_factory=dict)
    _econ: dict[tuple[str, ...], Dist] = field(init=False, default_factory=dict)
    _income_code: dict[str, np.ndarray] = field(init=False, default_factory=dict)
    _income_region: dict[str, np.ndarray] = field(init=False, default_factory=dict)
    _edu_national: dict[tuple[str, ...], Dist] = field(init=False, default_factory=dict)
    _firm_rel: dict[tuple[str, str], float] = field(init=False, default_factory=dict)
    _firm_obj: dict[tuple[str, str], dict[str, float]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        t = self.tables
        keys = ["sex", "age_class", "education"]
        for name, df in (
            ("trust", t.trust),
            ("life_satisfaction", t.life_satisfaction),
            ("internet", t.internet),
            ("political_info", t.political_info),
            ("religion", t.religion),
        ):
            self._avq[name] = _dist_by_keys(df, keys, "category", "count")
            classi = set(df["age_class"].unique().to_list())
            self._young[name] = "6_24" if "6_24" in classi else "14_24"
        self._econ = _dist_by_keys(t.economic_judgement, ["region"], "category", "count")
        for (dim, code), sub in t.income_main_earner.group_by(
            ["dimension", "code"], maintain_order=True
        ):
            arr = np.zeros(5)
            for q, s in zip(sub["quintile"].to_list(), sub["share"].to_list(), strict=True):
                arr[int(q) - 1] = float(s)
            self._income_code[f"{dim}:{code}"] = arr / arr.sum()
        for (region,), sub in t.income_region.group_by(["region"], maintain_order=True):
            arr = np.zeros(5)
            for q, s in zip(sub["quintile"].to_list(), sub["share"].to_list(), strict=True):
                arr[int(q) - 1] = float(s)
            self._income_region[str(region)] = arr / arr.sum()
        self._edu_national = _dist_by_keys(
            t.education_national, ["sex", "age_class"], "education", "count"
        )
        for row in t.firm_relations.iter_rows(named=True):
            self._firm_rel[(row["sector"], row["size_class"])] = (
                row["with_relations"] / row["total"]
            )
        for row in t.firm_objectives.iter_rows(named=True):
            self._firm_obj.setdefault((row["sector"], row["size_class"]), {})[row["objective"]] = (
                row["pursued"] / row["total"]
            )

    # ----------------------------------------------------------------- utilità

    @staticmethod
    def _draw(dist: Dist, rng: np.random.Generator) -> str:
        cats, p = dist
        return cats[int(rng.choice(len(cats), p=p))]

    def avq(self, name: str, sex: str, age: int, education: str, rng: np.random.Generator) -> str:
        key = (sex, avq_age_class(age, young=self._young[name]), education)
        dist = self._avq[name].get(key)
        if dist is None:
            raise ProfileError(f"{name}: nessuna distribuzione per {key}")
        return self._draw(dist, rng)

    def economic_judgement(self, region: str, rng: np.random.Generator) -> str:
        dist = self._econ.get((region,))
        if dist is None:
            raise ProfileError(f"giudizio economico: regione {region} assente")
        return self._draw(dist, rng)

    def income_quintile(
        self, education: str, status: str, region: str, rng: np.random.Generator
    ) -> int:
        """Quintile da P(q|titolo), P(q|condizione) e P(q|regione), assunte indipendenti."""
        split = self.priors.income
        if education == "fino_media":
            p_edu = sum(
                w * self._income_code[f"education:{c}"] for c, w in split.education_split.items()
            )
        elif education == "diploma":
            p_edu = self._income_code["education:7"]
        else:
            p_edu = self._income_code["education:11"]
        if status == "occupato":
            p_sta = sum(
                w * self._income_code[f"employment:{'1A' if k == 'indipendente' else '1B'}"]
                for k, w in split.employed_split.items()
            )
        elif status == "indipendente":
            p_sta = self._income_code["employment:1A"]
        elif status == "dipendente":
            p_sta = self._income_code["employment:1B"]
        else:
            codice = {"pensionato": "2A", "in_cerca": "2B", "altro_inattivo": "2C"}[status]
            p_sta = self._income_code[f"employment:{codice}"]
        p_reg = self._income_region[region]
        p = p_edu * p_sta * p_reg / (0.2**2)
        p = p / p.sum()
        return int(rng.choice(5, p=p)) + 1

    def education_for_firm_respondent(self, sex: str, age: int, rng: np.random.Generator) -> str:
        dist = self._edu_national[(sex, lfs_age_class(age))]
        return self._draw(dist, rng)

    def beta(self, prior: BetaPrior, context: Mapping[str, Any], rng: np.random.Generator) -> float:
        m = prior.base
        for dim, mapping in prior.modifiers.items():
            v = context.get(dim)
            if v is not None and str(v) in mapping:
                m += mapping[str(v)]
        m = float(np.clip(m, 0.05, 0.95))
        return float(rng.beta(m * prior.concentration, (1 - m) * prior.concentration))

    def name_for(
        self, sex: str, age: int, rng: np.random.Generator, reference_year: int = 2025
    ) -> str:
        if self.names is None:
            raise ProfileError("nomi non caricati")
        nascita = reference_year - age
        decennio = max(min((nascita // 10) * 10, max(self.names.decades)), min(self.names.decades))
        lista = (self.names.f if sex == "f" else self.names.m)[decennio]
        return lista[int(rng.integers(len(lista)))]

    # ------------------------------------------------------------- individui

    def individual(
        self, unit: Mapping[str, Any], rng: np.random.Generator
    ) -> tuple[dict[str, Any], dict[str, Provenance]]:
        sex, age, edu, emp, region = (
            unit["sex"],
            int(unit["age"]),
            unit["education"],
            unit["employment"],
            unit["region"],
        )
        prov: dict[str, Provenance] = {
            k: Provenance.CAMPIONE
            for k in ("region", "macro_area", "sex", "age", "age_band", "education", "employment")
        }
        if unit.get("source") == "lista_clienti":
            # Anagrafica (M13): territorio, sesso ed età dal file; il resto da ISTAT.
            for k in ("region", "macro_area", "sex", "age", "age_band"):
                prov[k] = Provenance.ANAGRAFICA
            prov["education"] = prov["employment"] = Provenance.ISTAT
        out: dict[str, Any] = {}
        out["income_quintile"] = self.income_quintile(edu, emp, region, rng)
        prov["income_quintile"] = Provenance.ISTAT
        out["economic_judgement"] = self.economic_judgement(region, rng)
        prov["economic_judgement"] = Provenance.ISTAT
        for name in ("trust", "internet", "political_info", "religion"):
            out[name] = self.avq(name, sex, age, edu, rng)
            prov[name] = Provenance.ISTAT
        out["life_satisfaction"] = int(self.avq("life_satisfaction", sex, age, edu, rng))
        prov["life_satisfaction"] = Provenance.ISTAT
        context = {**unit, **out}
        for name, prior in self.priors.traits.items():
            out[name] = self.beta(prior, context, rng)
            prov[name] = Provenance.IPOTESI
        for name, prior in self.priors.response_style.items():
            out[name] = self.beta(prior, context, rng)
            prov[name] = Provenance.IPOTESI
        return out, prov

    # ---------------------------------------------------------------- imprese

    def firm(
        self,
        unit: Mapping[str, Any],
        allowed_roles: list[str] | None,
        rng: np.random.Generator,
    ) -> tuple[dict[str, Any], dict[str, Provenance]]:
        sector, size_class, region = unit["sector"], unit["size_class"], unit["region"]
        prov: dict[str, Provenance] = {
            k: Provenance.CAMPIONE for k in ("region", "macro_area", "sector", "size_class")
        }
        da_anagrafica = unit.get("source") == "lista_clienti"
        if da_anagrafica:
            prov["region"] = prov["macro_area"] = Provenance.ANAGRAFICA
            prov["sector"] = Provenance.ANAGRAFICA if unit.get("sector_known") else Provenance.ISTAT
            prov["size_class"] = (
                Provenance.ANAGRAFICA if unit.get("size_known") else Provenance.ISTAT
            )
        out: dict[str, Any] = {}
        quote = dict(self.priors.respondent_roles[size_class])
        ruolo_noto = unit.get("respondent_role_known")
        if da_anagrafica and ruolo_noto in quote:
            quote = {str(ruolo_noto): 1.0}
        if allowed_roles:
            quote = {r: q for r, q in quote.items() if r in allowed_roles}
            if not quote:
                raise ProfileError(f"nessun ruolo ammesso per la classe {size_class}")
        ruoli = list(quote)
        p = np.array([quote[r] for r in ruoli])
        out["respondent_role"] = ruoli[int(rng.choice(len(ruoli), p=p / p.sum()))]
        prov["respondent_role"] = Provenance.IPOTESI
        lo, hi = self.priors.employees[size_class]
        out["employees"] = round(np.exp(rng.uniform(np.log(lo), np.log(hi + 1))))
        out["employees"] = min(max(out["employees"], lo), hi)
        prov["employees"] = Provenance.IPOTESI
        ruolo = out["respondent_role"]
        fr = self.priors.firm_respondent
        out["sex"] = "f" if rng.random() < fr.female_share[ruolo] else "m"
        a_lo, a_hi = fr.age_range[ruolo]
        out["age"] = int(rng.integers(a_lo, a_hi + 1))
        prov["sex"] = prov["age"] = Provenance.IPOTESI
        if da_anagrafica and unit.get("sex") in ("m", "f"):
            out["sex"] = str(unit["sex"])
            prov["sex"] = Provenance.ANAGRAFICA
        if da_anagrafica and unit.get("age") not in (None, ""):
            out["age"] = int(unit["age"])
            prov["age"] = Provenance.ANAGRAFICA
        if da_anagrafica and ruolo_noto in self.priors.respondent_roles[size_class]:
            prov["respondent_role"] = Provenance.ANAGRAFICA
        out["education"] = self.education_for_firm_respondent(out["sex"], out["age"], rng)
        prov["education"] = Provenance.ISTAT
        out["employment"] = "occupato"
        prov["employment"] = Provenance.IPOTESI
        status = "indipendente" if ruolo == "titolare" else "dipendente"
        out["income_quintile"] = self.income_quintile(out["education"], status, region, rng)
        prov["income_quintile"] = Provenance.ISTAT
        out["economic_judgement"] = self.economic_judgement(region, rng)
        prov["economic_judgement"] = Provenance.ISTAT
        rel = self._firm_rel.get((sector, size_class))
        if rel is None:
            raise ProfileError(f"relazioni imprese: {sector}/{size_class} assente")
        out["with_relations"] = bool(rng.random() < rel)
        prov["with_relations"] = Provenance.ISTAT
        chiave = (sector, size_class if size_class != "micro" else "piccola")
        obiettivi = self._firm_obj.get(chiave, {})
        out["objectives"] = [o for o, share in obiettivi.items() if rng.random() < share]
        prov["objectives"] = Provenance.ISTAT if size_class != "micro" else Provenance.ISTAT_PROXY
        for name in ("trust", "internet", "political_info", "religion"):
            out[name] = self.avq(name, out["sex"], out["age"], out["education"], rng)
            prov[name] = Provenance.ISTAT
        out["life_satisfaction"] = int(
            self.avq("life_satisfaction", out["sex"], out["age"], out["education"], rng)
        )
        prov["life_satisfaction"] = Provenance.ISTAT
        context = {**unit, **out, "age_band": _age_band(out["age"])}
        for name, prior in self.priors.traits.items():
            out[name] = self.beta(prior, context, rng)
            prov[name] = Provenance.IPOTESI
        for name, prior in self.priors.response_style.items():
            extra = self.priors.firm_response_style.get(name, {})
            prior_f = prior.model_copy(update={"modifiers": {**prior.modifiers, **extra}})
            out[name] = self.beta(prior_f, context, rng)
            prov[name] = Provenance.IPOTESI
        return out, prov


def _age_band(age: int) -> str:
    for band in cat.AGE_BANDS:
        if band.endswith("_plus"):
            return band
        lo, hi = (int(x) for x in band.split("_"))
        if lo <= age <= hi:
            return band
    raise AssertionError("fasce non contigue")
