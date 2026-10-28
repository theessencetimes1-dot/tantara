#!/usr/bin/env python3
"""Orchestrator probe: /query + /api/v1/ai/ask answer grounding and honesty.

Every citation must point at a real page whose text actually contains the quoted
passage; a query with no evidence must produce an honest no-evidence state, never a
plausible answer. Run: python scripts/verify_query.py http://127.0.0.1:<port> <data_dir>
"""
import json, re, sqlite3, sys, urllib.error, urllib.request

BASE = sys.argv[1].rstrip("/")
DATA = sys.argv[2]
FAILS = []


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def call(method, path, token=None, body=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, data, timeout=180) as r:
            raw, status, headers = r.read().decode("utf-8", "replace"), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, headers = e.read().decode("utf-8", "replace"), e.code, dict(e.headers)
    expects = expect if isinstance(expect, tuple) else (expect,)
    ok = status in expects
    print(f"{'OK      ' if ok else 'MISMATCH'} {method} {path} -> {status}")
    if not ok:
        FAILS.append(f"{method} {path} -> {status} expected {expects} body={raw[:200]}")
    try:
        return status, json.loads(raw), headers
    except Exception:
        return status, {"_raw": raw[:200]}, headers


def main():
    adv = (call("POST", "/api/v1/auth/login", body={"email": "advocate@tantara.local",
                                                     "password": "tantara-local"})[1] or {}).get("access_token")
    res = (call("POST", "/api/v1/auth/login", body={"email": "researcher@tantara.local",
                                                     "password": "tantara-local"})[1] or {}).get("access_token")
    _, me, _ = call("POST", "/api/v1/auth/login", body={"email": "advocate@tantara.local", "password": "tantara-local"})
    advocate_id = (me.get("user") or {}).get("id")
    _, m2, _ = call("POST", "/api/v1/auth/login", body={"email": "researcher@tantara.local", "password": "tantara-local"})
    researcher_id = (m2.get("user") or {}).get("id")
    _, cases, _ = call("GET", "/api/v1/cases?page_size=5", adv, expect=200)
    case = cases["items"][0]

    _, st, _ = call("GET", "/api/v1/ai/status", adv, expect=200)
    print(f"ai/status: {json.dumps(st)[:220]}")
    _, stt, _ = call("GET", "/api/v1/settings/ai", adv, expect=200)
    print(f"settings/ai keys: {sorted(stt.keys())}")

    call("POST", "/query", None, body={"question": "Where is the seat of arbitration?"}, expect=(401, 403))
    call("POST", "/api/v1/ai/ask", None, body={"question": "Where is the seat of arbitration?"}, expect=401)
    call("POST", "/query", adv, body={"question": "ab"}, expect=422)
    call("POST", "/query", adv, body={"question": "Where is the seat?", "top_k": 0}, expect=422)
    call("POST", "/query", adv, body={"question": "Where is the seat?", "top_k": 99}, expect=422)

    q = "Which city is the seat of arbitration in this matter, and which statute says so?"
    st, ans, _ = call("POST", "/query", adv, body={"question": q, "case_id": case["id"], "top_k": 6}, expect=200)
    keys = sorted(ans.keys())
    print(f"/query keys: {keys}")
    print(f"answer: {str(ans.get('answer') or ans.get('content'))[:320]}")
    print(f"status: {ans.get('status')}  degraded: {ans.get('degraded')} model: {ans.get('model')}")
    cits = ans.get("citations") or ans.get("sources") or []
    print(f"citations: {len(cits)}")
    if not cits:
        FAILS.append("a question the seeded corpus plainly answers returned no citations")
    db = sqlite3.connect(f"{DATA}/tantara.db")

    def page_text(doc_id, page_no):
        row = db.execute("select text from document_pages where document_id=? and page_number=?",
                         (doc_id, page_no)).fetchone()
        if row:
            return row[0] or ""
        return (db.execute("select text_content from documents where id=?", (doc_id,)).fetchone() or [""])[0]

    print(f"citation keys: {sorted(cits[0].keys()) if cits else '-'}")
    seen_pages = set()
    for c in cits[:6]:
        did = c.get("document_id") or c.get("id")
        pg = c.get("page_number") or c.get("page")
        quote = c.get("quote") or c.get("snippet") or c.get("text") or c.get("excerpt") or ""
        pc = db.execute("select page_count from documents where id=?", (did,)).fetchone()
        label = c.get("title") or c.get("document_title") or c.get("doc_title") or c.get("filename")
        print(f"  cite doc={str(did)[:8]} page={pg} of {pc} label={str(label)[:34]!r} quote={quote[:56]!r}")
        if not did or not isinstance(pg, int) or pg < 1:
            FAILS.append(f"citation lacks a usable document/page pointer: {json.dumps(c)[:160]}")
            continue
        if pc and pg > pc[0]:
            FAILS.append(f"citation points at page {pg} but the document has {pc[0]} pages")
        full = page_text(did, pg)
        if quote and norm(quote)[:120] not in norm(full):
            FAILS.append(f"citation quote is not present on the cited page (doc {str(did)[:8]} p{pg}): {quote[:80]!r}")
        seen_pages.add((did, pg))
        if not (c.get("title") or c.get("document_title") or c.get("filename")):
            FAILS.append(f"citation exposes no human-readable document label: {json.dumps(c)[:140]}")
        for k in c.keys():
            if "confidence" in k.lower():
                FAILS.append(f"ranking value is labelled {k} instead of relevance/score")

    _, ans2, _ = call("POST", "/api/v1/ai/ask", adv, body={"question": q, "case_id": case["id"], "top_k": 6}, expect=200)
    cits2 = ans2.get("citations") or ans2.get("sources") or []
    print(f"/api/v1/ai/ask citations: {len(cits2)} status={ans2.get('status')}")
    p2 = {(c.get("document_id") or c.get("id"), c.get("page_number") or c.get("page")) for c in cits2}
    if p2 and seen_pages and not (p2 & seen_pages):
        FAILS.append("/query and /api/v1/ai/ask retrieve disjoint evidence for the same question")

    # no-evidence honesty
    _, noise, _ = call("POST", "/query", adv, body={"question": "zzyz quuxorp plinth vexillometry",
                                                    "case_id": case["id"], "top_k": 5}, expect=200)
    ncit = noise.get("citations") or noise.get("sources") or []
    txt = str(noise.get("answer") or noise.get("content") or "")
    print(f"noise query: status={noise.get('status')} citations={len(ncit)} answer={txt[:180]!r}")
    if ncit:
        FAILS.append(f"a nonsense query still returned {len(ncit)} citations - retrieval has no evidence floor")
    # Honesty gate. Wording drift measured by the orchestrator at 05:5x UTC against the
    # merged backend: /query now returns status=insufficient_evidence with
    # "No indexed excerpt directly answers this question." (older build said
    # "There is insufficient evidence in the indexed documents …"). Both are accepted;
    # a vague answer that does not state the evidence gap still fails.
    if not re.search(r"insufficient evidence|no evidence|not enough evidence|no .*match|cannot|unable|could not find|no indexed excerpt|does not (directly )?answer|no supporting excerpt", txt, re.I):
        FAILS.append(f"the no-evidence answer does not say it lacks evidence: {txt[:160]!r}")

    # authorisation scope: researcher must not reach the advocate's matter
    _, rans, _ = call("POST", "/query", res, body={"question": q, "case_id": case["id"], "top_k": 4}, expect=(200, 403, 404))
    if rans.get("_raw"):
        pass
    else:
        rc = rans.get("citations") or rans.get("sources") or []
        foreign = []
        for c in rc:
            row = db.execute("select owner_id from documents where id=?", (c.get("document_id") or c.get("id"),)).fetchone()
            if row and row[0] != researcher_id:
                foreign.append(c)
        print(f"researcher /query: status={rans.get('status')} citations={len(rc)} foreign-owner={len(foreign)}")
        if foreign:
            FAILS.append(f"researcher was served {len(foreign)} documents owned by another user")

    if FAILS:
        print("\nQUERY PROBE FAILURES:")
        for f in FAILS:
            print(" -", f)
        sys.exit(1)
    print("\nALL QUERY/ANSWER-GROUNDING EXPECTATIONS PASSED")


main()
