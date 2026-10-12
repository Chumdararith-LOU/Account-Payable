"""Compare two pipeline dump JSONs (from scripts/dump_pipeline_output.py) and
print a structured diff report to stdout.

Usage:
  python scripts/compare_json_dumps.py /tmp/dump_mac.json /tmp/dump_server.json

Tolerances: text/html/fields exact; bbox +/-1 pixel per coordinate;
confidence +/-0.01. Exit 0 if no differences, 1 if any.
"""

from __future__ import annotations

import json
import sys

BBOX_TOL = 1
CONF_TOL = 0.01


def _bbox_close(a, b) -> bool:
    return all(abs(x - y) <= BBOX_TOL for x, y in zip(a, b))


def _conf_close(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # +1e-9: float error (abs(0.92-0.93) == 0.010000000000000009) must not
    # push an exactly-at-tolerance pair over the boundary.
    return abs(a - b) <= CONF_TOL + 1e-9


def _env_line(d: dict) -> str:
    e = d["environment"]
    return f"python={e['python_version']}, paddle={e['paddle_version']}"


def _compare_ocr(doc_a: dict, doc_b: dict, diffs: list) -> None:
    path = doc_a["path"]
    blocks_a = doc_a["ocr"]["text_blocks"]
    blocks_b = doc_b["ocr"]["text_blocks"]
    print(f"{path}:")
    print(f"  Mac: {len(blocks_a)} blocks, Server: {len(blocks_b)} blocks")
    n = min(len(blocks_a), len(blocks_b))
    differing = 0
    for i in range(n):
        a, b = blocks_a[i], blocks_b[i]
        if a["text"] != b["text"] or not _bbox_close(a["bbox"], b["bbox"]) or not _conf_close(a["conf"], b["conf"]):
            differing += 1
            diffs.append(f"ocr[{path}][{i}]")
            if a["text"] != b["text"]:
                print(f"    [{i}] Mac={a['text']!r} Server={b['text']!r}")
            else:
                print(f"    [{i}] text={a['text']!r} bbox Mac={a['bbox']} Server={b['bbox']} conf Mac={a['conf']} Server={b['conf']}")
    if len(blocks_a) != len(blocks_b):
        diffs.append(f"ocr-count[{path}]")
        print(f"    block count differs: Mac={len(blocks_a)} Server={len(blocks_b)}")
    if differing == 0 and len(blocks_a) == len(blocks_b):
        print("  Differences: none")
    else:
        print(f"  Summary: {differing} differing blocks")

    tables_a, tables_b = doc_a["tables"], doc_b["tables"]
    if len(tables_a) != len(tables_b):
        diffs.append(f"tables-count[{path}]")
        print(f"  tables: count differs Mac={len(tables_a)} Server={len(tables_b)}")
    for i, (ta, tb) in enumerate(zip(tables_a, tables_b)):
        if ta["html"] != tb["html"] or not _bbox_close(ta["bbox"], tb["bbox"]):
            diffs.append(f"tables[{path}][{i}]")
            print(f"  tables[{i}] differ (html equal: {ta['html'] == tb['html']})")


def _compare_parsed(doc_a: dict, doc_b: dict, diffs: list) -> None:
    pa, pb = doc_a["parsed"], doc_b["parsed"]
    if pa is None or pb is None:
        return
    kind = pa["kind"]
    fa, fb = pa["fields"], pb["fields"]
    print(f"{kind}:")
    field_diffs = 0
    for key in sorted(set(fa) | set(fb)):
        if key == "line_items":
            continue
        if fa.get(key) != fb.get(key):
            field_diffs += 1
            diffs.append(f"parsed[{kind}].{key}")
            print(f"  {key}:")
            print(f"    Mac:    {fa.get(key)!r}")
            print(f"    Server: {fb.get(key)!r}")
    la, lb = fa.get("line_items", []), fb.get("line_items", [])
    if len(la) != len(lb):
        field_diffs += 1
        diffs.append(f"parsed[{kind}].line_items-count")
        print(f"  line_items count differs: Mac={len(la)} Server={len(lb)}")
    for i, (xa, xb) in enumerate(zip(la, lb)):
        for key in sorted(set(xa) | set(xb)):
            if xa.get(key) != xb.get(key):
                field_diffs += 1
                diffs.append(f"parsed[{kind}].line_items[{i}].{key}")
                print(f"  line_items[{i}].{key}:")
                print(f"    Mac:    {xa.get(key)!r}")
                print(f"    Server: {xb.get(key)!r}")
    if field_diffs == 0:
        print("  Differences: none")
    else:
        print(f"  Summary: {field_diffs} field differences")


def _compare_pipeline(a: dict, b: dict, diffs: list) -> None:
    for section in ("validation", "match", "decision"):
        sa, sb = a["pipeline"][section], b["pipeline"][section]
        print(f"{section}:")
        if section == "match":
            print(f"  Mac:    outcome={sa['outcome']} score={sa['score']}")
            print(f"  Server: outcome={sb['outcome']} score={sb['score']}")
        elif section == "decision":
            print(f"  Mac:    route={sa['route']} reason={sa['reason']} score={sa['score']}")
            print(f"  Server: route={sb['route']} reason={sb['reason']} score={sb['score']}")
        if sa == sb:
            print("  Differences: none")
        else:
            diffs.append(f"pipeline.{section}")
            for key in sorted(set(sa) | set(sb)):
                if sa.get(key) != sb.get(key):
                    print(f"  {key}:")
                    print(f"    Mac:    {sa.get(key)!r}")
                    print(f"    Server: {sb.get(key)!r}")
    if a["pipeline"]["input_hash"] == b["pipeline"]["input_hash"]:
        print(f"input_hash: identical ({a['pipeline']['input_hash'][:16]}...)")
    else:
        diffs.append("pipeline.input_hash")
        print("input_hash: DIFFERS")
        print(f"  Mac:    {a['pipeline']['input_hash']}")
        print(f"  Server: {b['pipeline']['input_hash']}")


def main() -> int:
    with open(sys.argv[1]) as f:
        a = json.load(f)
    with open(sys.argv[2]) as f:
        b = json.load(f)

    diffs: list[str] = []

    print("=== ENVIRONMENT ===")
    print(f"mac:    {_env_line(a)}")
    print(f"server: {_env_line(b)}")
    if a["environment"]["paddle_version"] != b["environment"]["paddle_version"]:
        diffs.append("environment.paddle_version")

    print()
    print("=== OCR TEXT BLOCKS ===")
    docs_b = {d["path"]: d for d in b["documents"]}
    for doc_a in a["documents"]:
        doc_b = docs_b.get(doc_a["path"])
        if doc_b is None:
            diffs.append(f"missing-doc[{doc_a['path']}]")
            print(f"{doc_a['path']}: MISSING on server")
            continue
        _compare_ocr(doc_a, doc_b, diffs)
    for path in docs_b:
        if path not in {d["path"] for d in a["documents"]}:
            diffs.append(f"missing-doc[{path}]")
            print(f"{path}: MISSING on mac")

    print()
    print("=== PARSED DOCUMENTS ===")
    for doc_a in a["documents"]:
        if doc_a["parsed"] is None:
            continue
        doc_b = docs_b.get(doc_a["path"])
        if doc_b is not None and doc_b["parsed"] is not None:
            _compare_parsed(doc_a, doc_b, diffs)

    print()
    print("=== PIPELINE ===")
    _compare_pipeline(a, b, diffs)

    print()
    print("=== SUMMARY ===")
    ocr_diffs = sum(1 for d in diffs if d.startswith(("ocr", "tables")))
    field_diffs = sum(1 for d in diffs if d.startswith("parsed"))
    pipe_diffs = sum(1 for d in diffs if d.startswith(("pipeline", "environment", "missing-doc")))
    print(f"OCR diffs:       {ocr_diffs}")
    print(f"Field diffs:     {field_diffs}")
    print(f"Pipeline diffs:  {pipe_diffs}")
    print()
    print(f"DIFFERENCES: {len(diffs)}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
