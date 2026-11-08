#!/usr/bin/env python3
"""Post-deploy smoke for the LAN (k3s) TANTRA workspace.

Checks the parts of the deployment that actually break: the ingress routes, the
Postgres/hybrid-retrieval path, object storage, and — since 8 Nov — the Anthropic
answer path that replaced the offline LAN model. Prints no secrets.

    backend/.venv/bin/python scripts/lan_smoke.py [--base https://tantra.theessencetimes.com]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request

DEFAULT_BASE = "https://tantra.theessencetimes.com"
DEFAULT_EMAIL = "advocate@tantara.local"
PASSWORD_FILE = pathlib.Path.home() / ".config" / "tantara" / "tantara-demo-password"


def call(base: str, method: str, path: str, payload=None, token: str | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    # Cloudflare's browser-signature rule answers 1010 to the default urllib agent,
    # which would look like an outage rather than a deployment problem.
    req.add_header("user-agent", "Mozilla/5.0 (X11; Linux x86_64) TantraLanSmoke/1.0")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body[:200]
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--email", default=DEFAULT_EMAIL)
    ap.add_argument("--password-file", default=str(PASSWORD_FILE))
    args = ap.parse_args()

    base = args.base.rstrip("/")
    password = pathlib.Path(os.environ.get("TANTARA_DEMO_PASSWORD_FILE", args.password_file)).read_text(encoding="utf-8").strip()
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label:38s} {detail}")

    code, health = call(base, "GET", "/health")
    check("health", code == 200, str(health.get("version") if isinstance(health, dict) else health))

    code, auth = call(base, "POST", "/api/v1/auth/login", {"email": args.email, "password": password})
    token = auth.get("access_token") if isinstance(auth, dict) else None
    check("login", code == 200 and bool(token), f"as {args.email}")
    if not token:
        print(f"  cannot continue without a token: {str(auth)[:160]}")
        return 1

    code, me = call(base, "GET", "/api/v1/auth/me", token=token)
    check("session", code == 200 and isinstance(me, dict), f"role={me.get('role') if isinstance(me, dict) else me}")

    code, docs = call(base, "GET", "/api/v1/documents?page_size=50", token=token)
    items = docs.get("items") if isinstance(docs, dict) else None
    check("documents listed", code == 200 and isinstance(items, list), f"{len(items or [])} visible")

    code, sr = call(base, "GET", "/api/v1/search?query=termination+notice", token=token)
    hits = sr.get("results", sr.get("items")) if isinstance(sr, dict) else None
    check("hybrid retrieval", code == 200 and isinstance(hits, list), f"{len(hits or [])} hits")

    code, sess = call(base, "POST", "/api/v1/ai/sessions", {"title": "post-deploy smoke"}, token=token)
    sid = sess.get("id") if isinstance(sess, dict) else None
    check("research session", code == 200 and bool(sid))
    if sid:
        code, ans = call(base, "POST", f"/api/v1/ai/sessions/{sid}/messages", {"question": "What does the workspace say about notice periods?"}, token=token)
        if isinstance(ans, dict):
            check(
                "LLM answer via configured provider",
                code == 200 and ans.get("answer_kind") not in (None, "model_unavailable"),
                f"answer_kind={ans.get('answer_kind')} model={ans.get('model')} citations={len(ans.get('citations') or [])}",
            )
        else:
            check("LLM answer via configured provider", False, str(ans)[:160])

    code, tpl = call(base, "GET", "/api/v1/draft-templates", token=token)
    rows = tpl.get("items", tpl.get("templates")) if isinstance(tpl, dict) else tpl
    check("draft templates", code == 200 and isinstance(rows, list), f"{len(rows or [])} available")

    print(f"{'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}  against {base}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
