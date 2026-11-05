"""Ricognizione dell'API SDMX di ISTAT (strumento di sviluppo, non parte del pacchetto).

Uso:
    uv run python scripts/istat_explore.py search <parola> [<parola> ...]
    uv run python scripts/istat_explore.py dsd <id_struttura> [--codes]
    uv run python scripts/istat_explore.py flow <id_dataflow>
    uv run python scripts/istat_explore.py probe <id_dataflow> <chiave> [--start 2024] [--rows 20]

Le risposte della struttura vengono salvate in data/raw/_explore/ perché pesano
oltre 10 MB e il servizio è lento.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

BASE = "https://esploradati.istat.it/SDMXWS/rest"
CACHE = Path(__file__).resolve().parents[1] / "data" / "raw" / "_explore"
NS = {
    "m": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "c": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


def _get(url: str, accept: str | None = None, cache: bool = True) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{url}|{accept}".encode()).hexdigest()[:16]
    path = CACHE / f"{key}.txt"
    if cache and path.exists():
        return path.read_text(encoding="utf-8")
    headers = {"Accept": accept} if accept else {}
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0), follow_redirects=True) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")
    return r.text


def _name_it(el: ET.Element) -> str:
    for n in el.findall("c:Name", NS):
        if n.get("{http://www.w3.org/XML/1998/namespace}lang") == "it":
            return n.text or ""
    n = el.find("c:Name", NS)
    return (n.text or "") if n is not None else ""


def cmd_search(words: list[str]) -> None:
    root = ET.fromstring(_get(f"{BASE}/dataflow/IT1"))
    words_l = [w.lower() for w in words]
    for df in root.iter(f"{{{NS['s']}}}Dataflow"):
        name = _name_it(df)
        if all(w in name.lower() for w in words_l):
            ref = df.find("s:Structure/Ref", NS)
            dsd = ref.get("id") if ref is not None else "?"
            print(f"{df.get('id'):40} {dsd:28} {name}")


def cmd_flow(flow_id: str) -> None:
    root = ET.fromstring(_get(f"{BASE}/dataflow/IT1/{flow_id}/latest?references=all"))
    for df in root.iter(f"{{{NS['s']}}}Dataflow"):
        print("dataflow:", df.get("id"), "|", _name_it(df))
        ref = df.find("s:Structure/Ref", NS)
        if ref is not None:
            print("dsd:", ref.get("id"))
    for cons in root.iter(f"{{{NS['s']}}}ContentConstraint"):
        print("constraint:", cons.get("id"))
        for kv in cons.iter(f"{{{NS['c']}}}KeyValue"):
            vals = [v.text or "" for v in kv.findall("c:Value", NS)]
            print(f"  {kv.get('id')}: {len(vals)} valori -> {', '.join(vals[:25])}")


def cmd_dsd(dsd_id: str, codes: bool) -> None:
    root = ET.fromstring(_get(f"{BASE}/datastructure/IT1/{dsd_id}/latest?references=children"))
    codelists = {cl.get("id"): cl for cl in root.iter(f"{{{NS['s']}}}Codelist")}
    dsd = next(root.iter(f"{{{NS['s']}}}DataStructure"))
    print("dsd:", dsd.get("id"), "|", _name_it(dsd))
    for dim in dsd.iter(f"{{{NS['s']}}}Dimension"):
        if dim.get("position") is None:
            continue
        ref = dim.find("s:LocalRepresentation/s:Enumeration/Ref", NS)
        cl_id = ref.get("id") if ref is not None else "-"
        cl = codelists.get(cl_id)
        n = len(list(cl.iter(f"{{{NS['s']}}}Code"))) if cl is not None else 0
        print(f"  {dim.get('position'):>2}. {dim.get('id'):28} {cl_id:22} ({n} codici)")
        if codes and cl is not None:
            for code in cl.iter(f"{{{NS['s']}}}Code"):
                parent = code.find("s:Parent/Ref", NS)
                p = f" < {parent.get('id')}" if parent is not None else ""
                print(f"        {code.get('id'):16} {_name_it(code)[:70]}{p}")
    td = dsd.find(".//s:TimeDimension", NS)
    if td is not None:
        print(f"  time: {td.get('id')}")


def cmd_probe(flow_id: str, key: str, start: str | None, rows: int, summary: bool) -> None:
    url = f"{BASE}/data/{flow_id}/{key}"
    if start:
        url += f"?startPeriod={start}"
    text = _get(url, accept="application/vnd.sdmx.data+csv;version=1.0.0", cache=False)
    lines = text.splitlines()
    print(f"righe: {len(lines) - 1}")
    if summary:
        import csv
        from collections import Counter

        reader = csv.DictReader(lines)
        counters: dict[str, Counter[str]] = {}
        for row in reader:
            for col, val in row.items():
                if col.startswith("NOTE_") or col in {"DATAFLOW", "OBS_VALUE", "OBS_STATUS"}:
                    continue
                counters.setdefault(col, Counter())[val] += 1
        for col, cnt in counters.items():
            vals = ", ".join(f"{v}({n})" for v, n in sorted(cnt.items())[:40])
            print(f"  {col} [{len(cnt)}]: {vals}")
        return
    for line in lines[: rows + 1]:
        print(line)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("words", nargs="+")
    f = sub.add_parser("flow")
    f.add_argument("flow_id")
    d = sub.add_parser("dsd")
    d.add_argument("dsd_id")
    d.add_argument("--codes", action="store_true")
    pr = sub.add_parser("probe")
    pr.add_argument("flow_id")
    pr.add_argument("key")
    pr.add_argument("--start")
    pr.add_argument("--rows", type=int, default=20)
    pr.add_argument("--summary", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "search":
        cmd_search(a.words)
    elif a.cmd == "flow":
        cmd_flow(a.flow_id)
    elif a.cmd == "dsd":
        cmd_dsd(a.dsd_id, a.codes)
    elif a.cmd == "probe":
        cmd_probe(a.flow_id, a.key, a.start, a.rows, a.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
