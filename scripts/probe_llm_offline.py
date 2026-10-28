#!/usr/bin/env python3
"""Orchestrator probe: prove the app never fabricates an AI answer when the LLM is unreachable.

Run against a backend started with TANTARA_LOCAL_LLM_BASE_URL pointed at a dead port.
Usage: python3 scripts/probe_llm_offline.py [base_url]
Exits non-zero if any expectation fails. Prints its own evidence.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8168"
fails = []


def call(method, path, token=None, payload=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"content-type": "application/json", **({"authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:300]}


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


st, tok = call("POST", "/api/v1/auth/login", payload={"email": "advocate@tantara.local", "password": "tantara-local"})
check(st == 200 and tok.get("access_token"), f"login {st}")
token = tok["access_token"]

st, status = call("GET", "/api/v1/ai/status", token)
print("  ai/status.llm =", json.dumps(status.get("llm")))
check(st == 200 and status["llm"]["reachable"] is False, "ai/status reports llm.reachable=false")
check(status.get("embeddings", {}).get("ready") is True, "embeddings still ready while the LLM is down")

# A question whose answer exists in the indexed corpus: retrieval must still work,
# but the model cannot answer, so no invented prose may appear.
q = "What is the seat of arbitration?"
st, ask = call("POST", "/api/v1/ai/ask", token, {"question": q})
print("  ai/ask status/answer:", json.dumps({k: ask.get(k) for k in ("status", "model", "answer")})[:400])
check(st == 200, f"ai/ask returns 200 even when the model is down (got {st})")
check(ask.get("status") == "model_unavailable", f"ai/ask status is model_unavailable (got {ask.get('status')!r})")
ans = (ask.get("answer") or "").strip()
low = ans.lower()
# The contract that matters: the answer must be a truthful unavailability notice, never
# corpus-derived legal prose. The seeded corpus answer for this question is "Mumbai".
check(low == "" or "unavailable" in low, f"answer is an honest unavailability notice (answer={ans!r})")
check("mumbai" not in low and "seat shall be" not in low, "answer contains no corpus-derived assertion")
cits = ask.get("citations") or ask.get("cited_excerpts") or []
print(f"  NOTE   ai/ask citations while the model is down: {len(cits)} (retrieval-only endpoints are the supported path)")

st, qres = call("POST", "/query", token, {"question": "What is the seat of arbitration?"})
if st in (404, 405):
    st, qres = call("GET", "/query?question=arbitration", token)
supports = qres.get("supports") or []
detail = "status=%s total=%s supports=%s answer_kind=%s model=%s" % (
    st,
    qres.get("total"),
    len(supports),
    qres.get("answer_kind"),
    qres.get("model"),
)
check(st == 200 and bool(supports) and int(qres.get("total") or 0) > 0, "/query keeps retrieving without the LLM (%s)" % detail)

st, s2 = call("GET", "/api/v1/ai/status", token)
check(st == 200 and s2["llm"]["reachable"] is False, "ai/status stays honest on a second call")

print("\nOFFLINE-LLM EXPECTATIONS:", "PASSED" if not fails else f"{len(fails)} FAILED")
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
