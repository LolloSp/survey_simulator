"""Regole di coerenza fra attributi di una persona.

Due famiglie: violazioni "dure" che provocano una nuova estrazione degli
attributi assegnati in M4 (demografia e quote del campione non si toccano),
e avvisi su combinazioni rare ereditate dal campione, che restano ma vengono
contate nella diagnostica.
"""

from collections.abc import Mapping
from typing import Any


def hard_violations(attrs: Mapping[str, Any]) -> list[str]:
    """Combinazioni implausibili fra attributi assegnati: la persona va riestratta."""
    v: list[str] = []
    ls = int(attrs.get("life_satisfaction", 5))
    ej = attrs.get("economic_judgement")
    if ls <= 2 and ej == "ottime":
        v.append("soddisfazione minima con risorse economiche ottime")
    if ls >= 9 and ej == "insufficienti":
        v.append("soddisfazione massima con risorse economiche insufficienti")
    if attrs.get("internet") == "mai" and float(attrs.get("apertura_novita", 0)) > 0.8:
        v.append("mai su internet ma apertura al nuovo molto alta")
    if (
        attrs.get("employment") == "in_cerca"
        and int(attrs.get("income_quintile", 3)) == 5
        and int(attrs.get("age", 99)) < 30
    ):
        v.append("giovane in cerca di lavoro nel quintile di reddito più alto")
    if (
        attrs.get("respondent_role") == "responsabile_acquisti"
        and int(attrs.get("employees", 99)) < 5
    ):
        v.append("responsabile acquisti in impresa con meno di 5 addetti")
    if attrs.get("respondent_role") == "amministratore" and int(attrs.get("employees", 99)) < 2:
        v.append("amministratore in impresa con un solo addetto")
    return v


def sample_warnings(unit: Mapping[str, Any]) -> list[str]:
    """Combinazioni rare ma possibili ereditate dal campione (non si riestraggono)."""
    w: list[str] = []
    age = unit.get("age")
    if age is not None and unit.get("employment") == "pensionato" and int(age) < 50:
        w.append("pensionato sotto i 50 anni")
    if age is not None and unit.get("education") == "laurea_o_oltre" and int(age) < 21:
        w.append("laureato sotto i 21 anni")
    return w
