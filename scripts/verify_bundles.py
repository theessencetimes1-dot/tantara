"""Orchestrator proof of the filing-bundle backend: detail, generate, preview, download.

Self-contained: starts from nothing but the frozen envelopes and the seeded corpus.
Exits non-zero if any expectation fails, so a silent pass is impossible.
Usage: python3 verify_bundles.py http://127.0.0.1:8160
"""
import json
import re
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/")
FAILS = []


def call(method, path, token=None, body=None, expect=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    data = None if body is None else json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            raw, status, headers = r.read().decode("utf-8", "replace"), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, headers = e.read().decode("utf-8", "replace"), e.code, dict(e.headers)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"_raw": raw[:200]}
    tag = f"{method} {path} -> {status}"
    if expect is not None and status not in (expect if isinstance(expect, tuple) else (expect,)):
        FAILS.append(f"{tag} expected {expect} body={str(payload)[:220]}")
        print(f"MISMATCH {tag} body={str(payload)[:220]}")
    else:
        print(f"OK       {tag}")
    return status, payload, headers


def login(email):
    _, p, _ = call("POST", "/api/v1/auth/login", body={"email": email, "password": "tantara-local"}, expect=200)
    return p.get("access_token")


def pdf_pages(blob):
    if not blob.startswith(b"%PDF"):
        return None, "not a PDF (magic bytes wrong)"
    # /Count is written by pypdf/reportlab; fall back to counting page objects
    counts = [int(c) for c in re.findall(rb"/Count\s+(\d+)", blob)]
    objs = len(re.findall(rb"/Type\s*/Page[^s]", blob))
    n = max(counts) if counts else objs
    return n, f"counts={counts} page_objs={objs}"


def main():
    adv = login("advocate@tantara.local")
    ano = None

    # anonymous + cross-user authorisation
    call("GET", "/api/v1/bundles", expect=401)

    st, listing, _ = call("GET", "/api/v1/bundles", adv, expect=200)
    items = listing.get("items", [])
    print(f"advocate bundles: total={listing.get('total')} items={len(items)} keys={sorted(items[0].keys()) if items else 'none'}")
    if not items:
        FAILS.append("seeded advocate has no bundles - the seed is supposed to create one with 44 pages")

    rid = items[0]["id"] if items else None
    declared = None
    if rid:
        st, detail, _ = call("GET", f"/api/v1/bundles/{rid}", adv, expect=200)
        print(f"detail keys: {sorted(detail.keys())}")
        declared = detail.get("page_count") or detail.get("total_pages")
        print(f"bundle {rid} status={detail.get('status')} downloadable={detail.get('downloadable')} download_url={detail.get('download_url')} page_count={declared} settings={json.dumps(detail.get('settings'))[:220]}")

        # preview then download
        # contract: preview is a JSON page map, download is the merged PDF bytes
        st, prev, ph = call("GET", f"/api/v1/bundles/{rid}/preview", adv, expect=200)
        st2, dl, dh = call("GET", f"/api/v1/bundles/{rid}/download", adv, expect=200)
        if "_raw" in prev:
            FAILS.append(f"preview is not JSON: {str(prev)[:120]}")
        if "content-type" in {k.lower(): v for k, v in dh.items()} or True:
            ct = {k.lower(): v for k, v in dh.items()}.get("content-type", "")
            if "pdf" not in ct:
                FAILS.append(f"download content-type is {ct!r}, expected application/pdf")
        if isinstance(dl, dict) and "_raw" not in dl:
            FAILS.append("download returned a JSON object instead of the merged PDF")

    # binary truth: refetch preview/download as bytes
    prev_body = json.dumps(prev)
    for kind in ("preview", "download"):
        req = urllib.request.Request(f"{BASE}/api/v1/bundles/{rid}/{kind}")
        req.add_header("authorization", f"Bearer {adv}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                blob, ctype = r.read(), r.headers.get("content-type")
        except urllib.error.HTTPError as e:
            blob, ctype = e.read(), e.headers.get("content-type")
        n, how = pdf_pages(blob)
        print(f"{kind}: content-type={ctype} bytes={len(blob)} pages={n} ({how})")
        if kind == "download":
            if not blob.startswith(b"%PDF"):
                FAILS.append("download is not a PDF")
        elif not str(prev_body)[:1].startswith(("{", "[")):
            FAILS.append("preview is not a JSON page map")
        if kind == "download":
            if declared and n is not None and n != declared:
                FAILS.append(f"download renders {n} pages but the API declared page_count={declared}")
            if declared and n is None:
                FAILS.append("download could not be parsed for page count")
        else:
            # preview is a JSON page map (see the contract note above), so compare its
            # declared totals instead of parsing PDF pages out of a JSON body.
            pv_total = prev.get("total_pages") if isinstance(prev, dict) else None
            pv_sections = prev.get("sections") if isinstance(prev, dict) else None
            print(f"  preview contract: total_pages={pv_total} sections={len(pv_sections) if isinstance(pv_sections, list) else type(pv_sections).__name__}")
            if declared and pv_total is not None and pv_total != declared:
                FAILS.append(f"preview total_pages={pv_total} but bundle page_count={declared}")
            if declared and pv_total is None:
                FAILS.append("preview JSON exposes no total_pages to compare against page_count")

    # build a fresh bundle end to end so the merge path is proven, not just the seed
    _, cases, _ = call("GET", "/api/v1/cases?page_size=5", adv, expect=200)
    # The API rejects a bundle item whose document does not belong to the bundle's case
    # (404 "Document not found in this case"), so the probe must pick case-scoped documents.
    # Picking from an unfiltered document list used to grab an unassigned upload and made this
    # probe report a false failure.
    case, picked = None, []
    for cand in cases["items"]:
        _, cdocs, _ = call("GET", f"/api/v1/documents?case_id={cand['id']}&page_size=10", adv, expect=200)
        elig = [d for d in cdocs["items"] if (d.get("page_count") or 0) >= 2 and d.get("case_id") == cand["id"]]
        if len(elig) >= 2:
            case, picked = cand, elig[:2]
            break
        if elig and case is None:
            case, picked = cand, elig[:1]
    if case is None:
        case = cases["items"][0]
        print("  NOTE: no case has documents with a readable page_count; merge page check skipped")
    print(f"  merge-case={case['id'][:8]} picked={len(picked)} case-scoped documents")
    st, bundle, _ = call("POST", "/api/v1/bundles", adv,
                         body={"case_id": case["id"], "name": "Orchestrator merge proof"}, expect=(200, 201))
    bid = bundle.get("id")
    print(f"new bundle {bid} id present={bool(bid)}")
    wanted = []
    for i, d in enumerate(picked):
        pc = d.get("page_count") or 0
        lo, hi = (1, max(1, min(2, pc)))
        wanted.append({"document_id": d["id"], "page_start": lo, "page_end": hi, "section": "Documents", "order": i})
        print(f"  queued doc={d['id'][:8]} page_count={pc} range={lo}-{hi}")
    _, it, _ = call("PUT", f"/api/v1/bundles/{bid}/items", adv, body={"items": wanted}, expect=200)
    stored = it.get("items", [])
    print(f"PUT items -> stored {len(stored)} of {len(wanted)} (PUT replaces the whole list)")
    if len(stored) != len(wanted):
        FAILS.append(f"PUT items kept {len(stored)} of {len(wanted)} items")
    _, pv, _ = call("GET", f"/api/v1/bundles/{bid}/preview", adv, expect=200)
    secs, total, warns = pv.get("sections") or [], pv.get("total_pages"), pv.get("warnings")
    print(f"preview: total_pages={total} sections={secs if isinstance(secs, list) else list(secs)[:3]} warnings={warns}")
    if warns:
        FAILS.append(f"preview could not read source PDFs: {str(warns)[:160]}")
    if isinstance(secs, list) and not secs:
        FAILS.append("preview returned no sections after items were attached")
    st, gen, _ = call("POST", f"/api/v1/bundles/{bid}/generate", adv, body={}, expect=(200, 202))
    print(f"generate -> declared page_count={gen.get('page_count') or gen.get('total_pages')} status={gen.get('status')}")

    if not bid:
        FAILS.append("bundle creation failed - cannot exercise the generate/download path")
    req = urllib.request.Request(f"{BASE}/api/v1/bundles/{bid}/download")
    req.add_header("authorization", f"Bearer {adv}")
    with urllib.request.urlopen(req, timeout=60) as r:
        blob2, ctype2 = r.read(), r.headers.get("content-type")
    n2, how2 = pdf_pages(blob2)
    print(f"fresh download: content-type={ctype2} bytes={len(blob2)} pages={n2} ({how2})")
    if not blob2.startswith(b"%PDF"):
        FAILS.append("freshly generated bundle is not a PDF")
    expected_front = 4  # cover + index + synopsis + list of dates, per the seeded front-matter convention
    if n2 is not None and picked:
        want = expected_front + sum(min(2, d.get("page_count") or 0) for d in picked)
        print(f"expected roughly {want} pages (front matter {expected_front} + selected ranges)")
        if n2 != want:
            FAILS.append(f"merged PDF has {n2} pages, expected {want} (4 front matter + selected source pages)")
    elif n2 is not None:
        print(f"fresh PDF has {n2} pages; no case-scoped documents to merge, so only front matter is expected")
        if n2 != expected_front:
            FAILS.append(f"front-matter-only bundle has {n2} pages, expected {expected_front}")

    # validation: an out-of-range page request must be rejected, not silently clamped away
    if picked:
        d0 = picked[0]
        _, before_detail, _ = call("GET", f"/api/v1/bundles/{bid}", adv, expect=200)
        items_before = len(before_detail.get("items") or [])
        call("PUT", f"/api/v1/bundles/{bid}/items", adv,
             body={"items": [{"document_id": d0["id"], "page_start": 1, "page_end": 9999, "section": "Documents", "order": 0}]},
             expect=(400, 404, 409, 422))
        _, after_detail, _ = call("GET", f"/api/v1/bundles/{bid}", adv, expect=200)
        items_after = len(after_detail.get("items") or [])
        _, pv_after, _ = call("GET", f"/api/v1/bundles/{bid}/preview", adv, expect=200)
        print(f"after rejected range PUT: items {items_before} -> {items_after}, total_pages={pv_after.get('total_pages')} warnings={pv_after.get('warnings')}")
        if items_after != items_before:
            FAILS.append(f"a rejected out-of-range PUT changed stored items {items_before} -> {items_after}; the write is not atomic")

    # authorisation: a second user must not see this bundle
    res = login("staff@tantara.local")
    st, _, _ = call("GET", f"/api/v1/bundles/{bid}", res, expect=404)
    st, _, _ = call("GET", f"/api/v1/bundles/{bid}/download", res, expect=404)
    st, _, _ = call("GET", f"/api/v1/bundles/{rid}", ano, expect=401)

    if FAILS:
        print("\nBUNDLE PROBE FAILURES:")
        for f in FAILS:
            print(" -", f)
        sys.exit(1)
    print("\nALL BUNDLE DETAIL/PREVIEW/DOWNLOAD EXPECTATIONS PASSED")


main()
