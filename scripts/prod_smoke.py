#!/usr/bin/env python3
"""Post-deploy production smoke for the 1 Nov build: participant-fallback drafts,
grounded research, upload and extraction. Prints no secrets."""
import json
import time
import urllib.error
import urllib.request

SITE = "https://tantara-prod.web.app"


def call(method, path, payload=None, token=None, raw=False):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(SITE + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            body = resp.read()
            return resp.status, (body if raw else json.loads(body.decode()))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text[:200]


stamp = int(time.time())
status, account = call(
    "POST",
    "/api/v1/auth/register",
    {"name": "Deploy Smoke", "email": f"qa.smoke.{stamp}@theessencetimes.com", "password": "Tantra-Test-2026!", "title": "Advocate"},
)
token = account["access_token"]
print("register:", status)

status, case = call("POST", "/api/v1/cases", {"title": "Northstar Industries Ltd vs. Cedar Works LLC"}, token)
case_id = case["id"]
print("case (no claimant/respondent on the form):", status, "| claimant:", case.get("claimant") or "blank")

for name, role in (("Northstar Industries Ltd", "claimant"), ("Cedar Works LLC", "respondent")):
    st, _ = call("POST", f"/api/v1/cases/{case_id}/participants", {"name": name, "party_role": role}, token)
    print(f"participant {role}:", st)

boundary = "----tantraSmoke"
agreement = (
    "ARBITRATION AGREEMENT\nReference: TANTRA-SMOKE-2026-001.\n"
    "Between Northstar Industries Ltd (the Supplier) and Cedar Works LLC (the Buyer).\n"
    "Seat of arbitration: New Delhi. Sole arbitrator. Governing law: Indian law.\n"
)
body = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"Smoke-Agreement.txt\"\r\n"
    f"Content-Type: text/plain\r\n\r\n{agreement}\r\n--{boundary}--\r\n"
).encode()
req = urllib.request.Request(SITE + "/api/v1/documents/upload", data=body, method="POST")
req.add_header("content-type", f"multipart/form-data; boundary={boundary}")
req.add_header("authorization", f"Bearer {token}")
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        up = json.loads(resp.read().decode())
    doc_id = up.get("document_id") or up.get("document", {}).get("id")
    print("upload:", resp.status, doc_id)
except urllib.error.HTTPError as exc:
    print("upload failed:", exc.code, exc.read().decode()[:200])
    raise SystemExit(1)

st, _ = call("PATCH", f"/api/v1/documents/{doc_id}", {"case_id": case_id}, token)
print("link to case:", st)

doc_status = "unknown"
for _ in range(30):
    st, listed = call("GET", f"/api/v1/documents/{doc_id}", token=token)
    doc_status = listed.get("status")
    if doc_status in ("ready", "failed"):
        break
    time.sleep(3)
print("document status:", doc_status)

st, ai = call("POST", "/api/v1/ai/ask", {
    "question": "What is the seat of arbitration and how many arbitrators are provided for in the agreement?",
    "case_id": case_id,
    "top_k": 6,
}, token)
answer = (ai.get("answer") or "").replace("\n", " ")
print("research:", st, "| kind:", ai.get("answer_kind"), "| citations:", len(ai.get("citations", [])))
print("   mentions seat/arbitrator:", ("new delhi" in answer.lower(), "sole" in answer.lower() or "one" in answer.lower()))

st, extraction = call("POST", f"/api/v1/documents/{doc_id}/ai", {}, token)
fields = {item.get("field"): item.get("value") for item in (extraction.get("candidates") or extraction.get("fields") or [])}
print("extraction:", st, "| fields:", {k: v for k, v in list(fields.items())[:6]})

st, draft = call("POST", "/api/v1/drafts/generate", {
    "case_id": case_id,
    "document_type": "Notice Invoking Arbitration",
    "instructions": "Prepare a formal legal notice for non-payment under the supply agreement.",
    "source_document_ids": [doc_id],
}, token)
detail = draft.get("draft_id")
st2, record = call("GET", f"/api/v1/drafts/{detail}", token=token) if detail else (0, draft)
content = (record.get("content_markdown") or record.get("content") or draft.get("content_markdown") or "")
print("draft:", st, st2, "| generation_kind:", draft.get("generation_kind"), "| status:", draft.get("status"), "| chars:", len(content))
print("   caption from participants:", ("Northstar Industries Ltd" in content, "Cedar Works LLC" in content))
print("   placeholders:", content.count("[TO BE CONFIRMED]"))
for key in (account["access_token"], token):
    pass
