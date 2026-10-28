#!/usr/bin/env python3
"""Orchestrator probe: how reliable is strategy generation with the configured model?

The Strategy Advisor discards the model's whole response if any section fails
validation, so a single malformed citation id leaves the UI with an empty plan.
This script measures that rate against a running backend instead of guessing.

usage: python3 scripts/probe_strategy_reliability.py <base_url> [case_id] [runs]
Prints one line per run and a summary; exits 0 if the success rate is >= 80 %.
"""
import subprocess
import sys
import time

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8010"
RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 10
SECTIONS = ("case_theory", "key_issues", "legal_arguments", "counterarguments", "evidence_gaps", "strategy_plan")


def curl(method, path, token=None, payload=None, timeout=300):
    cmd = ["curl", "-s", "-m", str(timeout), "-X", method, BASE + path]
    if token:
        cmd += ["-H", f"authorization: Bearer {token}"]
    if payload is not None:
        cmd += ["-H", "content-type: application/json", "-d", payload]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    import json

    return json.loads(out) if out.strip().startswith(("{", "[")) else {"_raw": out[:200]}


tok = curl("POST", "/api/v1/auth/login", payload='{"email":"advocate@tantara.local","password":"tantara-local"}').get("access_token")
if not tok:
    print("login failed")
    sys.exit(2)
cid = len(sys.argv) > 2 and sys.argv[2]
if not cid:
    listing = curl("GET", "/api/v1/cases?page_size=5", tok)
    cid = listing["items"][0]["id"]
    print(f"using case {cid} ({listing['items'][0]['title']})")

ok = 0
partial = 0
for i in range(RUNS):
    t0 = time.time()
    d = curl("POST", f"/api/v1/cases/{cid}/strategy/generate", tok, "{}")
    kind = d.get("generation_kind")
    filled = [s for s in SECTIONS if d.get(s)]
    if kind == "model_strategy":
        ok += 1
        if len(filled) < len(SECTIONS):
            partial += 1
    print(
        f"  run {i + 1:2d}: kind={str(kind):<21} status={str(d.get('status')):<18} "
        f"sections_filled={len(filled)}/{len(SECTIONS)} citations={len(d.get('citations') or [])} "
        f"assertion_citations={len(d.get('assertion_citations') or [])} {time.time() - t0:.1f}s"
    )
    if kind == "template" and d.get("generation_note"):
        print(f"          note: {d['generation_note'][:120]}")

rate = ok / RUNS
print(f"\nSTRATEGY RELIABILITY: {ok}/{RUNS} model_strategy ({rate:.0%}), of which {partial} had empty sections")
print(f"gate: >=80% model_strategy -> {'PASS' if rate >= 0.8 else 'FAIL'}")
sys.exit(0 if rate >= 0.8 else 1)
