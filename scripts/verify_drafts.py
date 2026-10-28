#!/usr/bin/env python3
"""Orchestrator probe: draft versioning + restore semantics against a live backend.

Measured contract (backend/app/routers/drafts.py): POST /drafts/{rid}/versions snapshots the
CURRENT content and then optionally applies content_markdown; there is no PATCH/PUT on drafts,
so this endpoint is the only way an editor saves. Restore snapshots the current content, then
applies the selected version's content (non-destructive). Export supports docx|pdf and returns
409 when the draft is blank.
"""
import io, json, sys, urllib.error, urllib.request, zipfile

BASE = sys.argv[1].rstrip("/")
FAILS = []


def call(method, path, token=None, body=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            raw, status, headers = r.read().decode("utf-8", "replace"), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, headers = e.read().decode("utf-8", "replace"), e.code, dict(e.headers)
    expects = expect if isinstance(expect, tuple) else (expect,)
    ok = status in expects
    print(f"{'OK      ' if ok else 'MISMATCH'} {method} {path} -> {status}")
    if not ok:
        FAILS.append(f"{method} {path} -> {status} expected {expects} body={raw[:180]}")
    try:
        return status, json.loads(raw), headers
    except Exception:
        return status, {"_binary": True}, headers


def login(email):
    _, j, _ = call("POST", "/api/v1/auth/login", body={"email": email, "password": "tantara-local"})
    return j.get("access_token")


def versions_of(token, rid):
    _, lst, _ = call("GET", f"/api/v1/drafts/{rid}/versions", token, expect=200)
    vs = lst.get("items", lst.get("versions", []))
    return sorted(vs, key=lambda v: v.get("version_number") or 0)


def main():
    adv = login("advocate@tantara.local")
    res = login("researcher@tantara.local")
    staff = login("staff@tantara.local")
    _, cases, _ = call("GET", "/api/v1/cases?page_size=3", adv, expect=200)
    case = cases["items"][0]

    _, d, _ = call("POST", "/api/v1/drafts", adv,
                   body={"case_id": case["id"], "title": "Orchestrator versioning proof",
                         "document_type": "Written Statement"}, expect=(200, 201))
    rid = d.get("id")
    if not rid:
        print("FAILS: draft creation failed"); sys.exit(1)
    print(f"draft {rid} keys={sorted(d.keys())}")

    c1 = "First content. Clause 7 governs the arbitration seated in Mumbai."
    c2 = "Second content, deliberately different: counsel moved the seat to Delhi."

    call("POST", f"/api/v1/drafts/{rid}/versions", adv, body={"content_markdown": c1}, expect=(200, 201))
    _, g1, _ = call("GET", f"/api/v1/drafts/{rid}", adv, expect=200)
    if "Clause 7" not in (g1.get("content_markdown") or ""):
        FAILS.append("applying content through the version endpoint did not update the draft")

    _, v2, _ = call("POST", f"/api/v1/drafts/{rid}/versions", adv,
                    body={"content_markdown": c2, "change_note": "seat change"}, expect=(200, 201))
    _, g2, _ = call("GET", f"/api/v1/drafts/{rid}", adv, expect=200)
    body_now = g2.get("content_markdown") or ""
    print(f"after second save: {body_now[:52]!r}")
    if "Delhi" not in body_now:
        FAILS.append("the newest content was not applied to the draft")

    vs = versions_of(adv, rid)
    print(f"versions={[ (v.get('version_number'), (v.get('content_markdown') or '')[:22]) for v in vs ]}")
    nums = [v.get("version_number") for v in vs]
    if nums != sorted(nums) or len(set(nums)) != len(nums):
        FAILS.append(f"version numbers not unique/increasing: {nums}")
    snap = next((v for v in vs if "Clause 7" in (v.get("content_markdown") or "")), None)
    if not snap:
        FAILS.append("no version snapshot holds the previous content - history is not an audit trail")

    # whitespace-only save must not silently wipe the draft
    call("POST", f"/api/v1/drafts/{rid}/versions", adv, body={"content_markdown": "   \n  "}, expect=(400, 422))
    _, g3, _ = call("GET", f"/api/v1/drafts/{rid}", adv, expect=200)
    after_blank = g3.get("content_markdown") or ""
    print(f"content after a whitespace-only save attempt: {after_blank[:46]!r}")
    if not after_blank.strip():
        FAILS.append("a whitespace-only version save erased the draft content (the backend's own blank-patch rule is not applied on this route)")

    if snap:
        _, rst, _ = call("POST", f"/api/v1/drafts/{rid}/versions/{snap['id']}/restore", adv, body={}, expect=(200, 201))
        _, g4, _ = call("GET", f"/api/v1/drafts/{rid}", adv, expect=200)
        restored = g4.get("content_markdown") or ""
        print(f"restored content: {restored[:52]!r}")
        if "Clause 7" not in restored:
            FAILS.append(f"restore did not put the old content back ({restored[:70]!r})")
        vs2 = versions_of(adv, rid)
        print(f"history after restore: {len(vs2)} versions, notes={[ (v.get('version_number'), v.get('change_note')) for v in vs2[-2:] ]}")
        if len(vs2) <= len(vs):
            FAILS.append(f"restore destroyed history ({len(vs)} -> {len(vs2)})")
        nums2 = [v.get("version_number") for v in vs2]
        if len(set(nums2)) != len(nums2):
            FAILS.append(f"duplicate version numbers after restore: {nums2}")
        _, one, _ = call("GET", f"/api/v1/drafts/{rid}/versions/{snap['id']}", adv, expect=200)
        if "Clause 7" not in (one.get("content_markdown") or ""):
            FAILS.append("version detail does not return the snapshot content")
        if not any("Restored" in (v.get("change_note") or "") for v in vs2):
            FAILS.append("restore leaves no provenance note in the history")

    call("POST", f"/api/v1/drafts/{rid}/versions/00000000-0000-0000-0000-000000000000/restore", adv, body={}, expect=404)
    call("GET", f"/api/v1/drafts/{rid}/versions/{(snap or vs[0])['id']}", res, expect=404)
    # contract: another user's resources are masked as 404, not 403 (403 is reserved for
    # a *role* refusal, e.g. the read-only researcher). Accept either, prefer 404.
    call("POST", f"/api/v1/drafts/{rid}/versions/{(snap or vs[0])['id']}/restore", res, body={}, expect=(404, 403))
    call("POST", f"/api/v1/drafts/{rid}/versions/{(snap or vs[0])['id']}/restore", staff, body={}, expect=(404, 403))
    call("GET", f"/api/v1/drafts/{rid}", None, expect=401)
    call("GET", f"/api/v1/drafts/{rid}", res, expect=404)

    # export must carry the restored text (docx is a zip; read the document part)
    for fmt, magic, part in (("docx", b"PK\x03\x04", "word/document.xml"), ("pdf", b"%PDF", None)):
        req = urllib.request.Request(f"{BASE}/api/v1/drafts/{rid}/export?format={fmt}")
        req.add_header("authorization", f"Bearer {adv}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                blob, ctype = r.read(), r.headers.get("content-type")
        except Exception as e:
            FAILS.append(f"export {fmt} failed: {e}")
            continue
        text = ""
        if magic == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    text = z.read(part).decode("utf-8", "replace")
            except Exception as e:
                FAILS.append(f"export {fmt} is not a readable zip: {e}")
        else:
            # PDF text lives in compressed streams: decoding the raw bytes as latin-1
            # would never contain the literal body, so extract properly instead.
            text = ""
            try:
                import pypdfium2 as pdfium

                pdf = pdfium.PdfDocument(io.BytesIO(blob))
                text = "\n".join((p.get_textpage().get_text_range() or "") for p in pdf)
                print(f"  pdf pages={len(pdf)} extracted_chars={len(text)}")
            except Exception as exc:  # noqa: BLE001
                try:
                    import re
                    import zlib

                    for m in re.finditer(rb"stream\r?\n(.*?)endstream", blob, re.S):
                        try:
                            text += zlib.decompress(m.group(1)).decode("latin-1", "replace")
                        except Exception:
                            pass
                    print(f"  pypdfium2 unavailable ({exc}); fell back to zlib stream scan, chars={len(text)}")
                except Exception:
                    text = blob.decode("latin-1")
        print(f"export {fmt}: content-type={ctype} bytes={len(blob)} magic_ok={blob[:4] == magic} has_restored_text={'Clause 7' in text}")
        if blob[:4] != magic:
            FAILS.append(f"export {fmt} has wrong magic bytes {blob[:4]!r}")
        if "Clause 7" not in text:
            FAILS.append(f"export {fmt} does not contain the restored draft text")

    # a blank draft must refuse export honestly rather than emit an empty file
    _, empty_draft, _ = call("POST", "/api/v1/drafts", adv,
                             body={"case_id": case["id"], "title": "Blank export probe", "document_type": "Notice"},
                             expect=(200, 201))
    if empty_draft.get("id"):
        call("GET", f"/api/v1/drafts/{empty_draft['id']}/export", adv, expect=409)

    if FAILS:
        print("\nDRAFT PROBE FAILURES:")
        for f in FAILS:
            print(" -", f)
        sys.exit(1)
    print("\nALL DRAFT VERSIONING/RESTORE/EXPORT EXPECTATIONS PASSED")


main()
