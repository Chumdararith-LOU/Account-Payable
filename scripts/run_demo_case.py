#!/usr/bin/env python3
"""
Run a demo case against the deployed APMatch API.

Usage:
  python scripts/run_demo_case.py [--server URL] [--customer-id ID]
                                   [--fixtures DIR] [--without-embeddings]

Defaults:
  --server       http://100.88.94.91:8001
  --customer-id  demo
  --fixtures     documents/demo/

Behavior:
  1. Reads the API key from APMATCH_API_KEY env var.
     If not set, tries to read it from
     rith@100.88.94.91:/opt/apmatch/.env.server via SSH (fallback).
  2. POSTs the 4 fixtures to /match?customer_id=<id>.
  3. Fetches the audit row for the returned run_id.
  4. Prints a clean result summary.

Exit codes:
  0 — case ran successfully (any route is success for the demo)
  1 — network / auth / API error
  2 — missing fixtures or config

Stdlib only (urllib, argparse, json, sys, os, subprocess, uuid).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# /match form field name -> fixture file name (inside --fixtures dir).
FIXTURE_FIELDS = {
    "invoice": "invoice.png",
    "po": "po.png",
    "grni": "grn.png",
    "pard": "pard.png",
}

SSH_KEY_FALLBACK = (
    "ssh rith@100.88.94.91 "
    "'grep \"^APMATCH_API_KEY=\" /opt/apmatch/.env.server | cut -d= -f2'"
)


def die(code: int, msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def get_api_key() -> str:
    key = os.environ.get("APMATCH_API_KEY", "").strip()
    if key:
        return key
    # Fallback: read from the deployed server over SSH.
    try:
        out = subprocess.run(
            SSH_KEY_FALLBACK, shell=True, capture_output=True, text=True, timeout=30
        )
        key = out.stdout.strip()
    except Exception:
        key = ""
    if not key:
        die(2, "no API key. Set APMATCH_API_KEY or ensure SSH to the server works.")
    return key


def build_multipart(files: dict[str, bytes]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for field, data in files.items():
        filename = Path(field).name
        parts.append(f"--{boundary}".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"'.encode()
        )
        parts.append(b"Content-Type: image/png")
        parts.append(b"")
        parts.append(data)
    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    return b"\r\n".join(parts), f"multipart/form-data; boundary={boundary}"


def http_json(url: str, key: str, data: bytes | None = None,
              content_type: str | None = None, timeout: int = 600) -> dict:
    headers = {"X-API-Key": key}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(1, f"HTTP {e.code} from {url}: {body[:300]}")
    except urllib.error.URLError as e:
        die(1, f"cannot reach {url}: {e.reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run an APMatch demo case.")
    ap.add_argument("--server", default="http://100.88.94.91:8001")
    ap.add_argument("--customer-id", default="demo")
    ap.add_argument("--fixtures", default="documents/demo/")
    ap.add_argument("--without-embeddings", action="store_true")
    args = ap.parse_args()

    server = args.server.rstrip("/")
    fixtures = Path(args.fixtures)

    if args.without_embeddings:
        print("warning: --without-embeddings is not yet supported by the API — "
              "displaying with-embeddings output only.", file=sys.stderr)

    # Load fixtures (exit 2 if any missing).
    files: dict[str, bytes] = {}
    for field, fname in FIXTURE_FIELDS.items():
        p = fixtures / fname
        if not p.is_file():
            die(2, f"missing fixture: {p}")
        files[field] = p.read_bytes()

    key = get_api_key()

    # Header box.
    width = 52
    print("┌" + "─" * (width - 2) + "┐")
    print(f"│ APMatch demo case".ljust(width - 1) + "│")
    print(f"│ Server:   {server}".ljust(width - 1) + "│")
    print(f"│ Customer: {args.customer_id}".ljust(width - 1) + "│")
    for field, fname in FIXTURE_FIELDS.items():
        print(f"│ {field + ':':<10} {(fixtures / fname)}".ljust(width - 1) + "│")
    print("└" + "─" * (width - 2) + "┘")
    print()
    print("Running pipeline (this may take 30-90s)...")

    body, ctype = build_multipart(files)
    match_url = f"{server}/match?customer_id={args.customer_id}"
    result = http_json(match_url, key, data=body, content_type=ctype)

    route = result.get("route", "?")
    reason = result.get("route_reason", "?")
    score = result.get("score", 0.0)
    invoice = result.get("invoice_number", "?")
    remark = result.get("remark", "?")
    run_id = result.get("run_id", "?")
    sims = result.get("similarity_matches", []) or []

    print()
    print(f"Route:            {route}")
    print(f"Reason:           {reason}")
    print(f"Score:            {score:.4f}")
    print(f"Invoice number:   {invoice}")
    print(f"Remark:           {remark}")
    print()
    if sims:
        print(f"Similarity matches: {len(sims)}  (embedding fallback)")
        for s in sims:
            print(f"  - [{s.get('band', '?')}] {s.get('invoice_text', '?')} ~ "
                  f"{s.get('counterpart_text', '?')}  (score {s.get('score', '?')})")
    else:
        print("Similarity matches: 0")
        print("  (No fallback used — all line items matched exactly.)")

    # Fetch the audit row for the input hash + customer_id.
    print()
    print("Audit row:")
    print(f"  run_id:         {run_id}")
    try:
        audit = http_json(f"{server}/audit/{run_id}", key)
        print(f"  customer_id:    {audit.get('customer_id', '?')}")
        print(f"  input_hash:     {audit.get('input_hash', '?')}")
    except SystemExit:
        print("  (audit fetch failed — see error above)")

    sys.exit(0)


if __name__ == "__main__":
    main()
