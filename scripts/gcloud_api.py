#!/usr/bin/env python3
"""Call Google Cloud APIs with a service-account key, without gcloud.

The orchestrator-only helper for the production (Cloud Run + Firebase Hosting)
deployment. It never prints a credential: tokens are held in memory, the key
file is read from the path in $TANTARA_GSA_KEY, and only API responses are
written to stdout.

    TANTARA_GSA_KEY=sensitive/gcp-admin.json \
        backend/.venv/bin/python scripts/gcloud_api.py GET \
        https://run.googleapis.com/v2/projects/tantra-513216/locations/asia-south1/services

Scope defaults to cloud-platform; pass --scope to narrow it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import jwt
import requests

DEFAULT_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Minting a fresh access token for every call is slow and, observed on this
# project, occasionally makes Google's endpoints answer 401 while propagation
# catches up. One token per (key, scope) is reused until it is nearly expired.
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


def access_token(key_path: str, scope: str = DEFAULT_SCOPE) -> str:
    cached = _token_cache.get((key_path, scope))
    if cached and cached[1] > time.time() + 120:
        return cached[0]
    with open(key_path) as handle:
        key = json.load(handle)
    now = int(time.time())
    claims = {
        "iss": key["client_email"],
        "scope": scope,
        "aud": key["token_uri"],
        "iat": now,
        "exp": now + 3600,
    }
    assertion = jwt.encode(claims, key["private_key"], algorithm="RS256")
    if isinstance(assertion, bytes):
        assertion = assertion.decode()
    response = requests.post(
        key["token_uri"],
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SystemExit(f"token exchange failed: {response.status_code} {response.text[:200]}")
    payload = response.json()
    token = payload["access_token"]
    _token_cache[(key_path, scope)] = (token, time.time() + float(payload.get("expires_in", 3600)))
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method")
    parser.add_argument("url")
    parser.add_argument("--body", help="JSON string or @file")
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--key", default=os.environ.get("TANTARA_GSA_KEY", "sensitive/gcp-admin.json"))
    parser.add_argument("--quiet", action="store_true", help="print only HTTP status")
    args = parser.parse_args()

    token = access_token(args.key, args.scope)
    body = None
    if args.body:
        if args.body.startswith("@"):
            with open(args.body[1:]) as handle:
                body = json.load(handle)
        else:
            body = json.loads(args.body)
    response = requests.request(
        args.method,
        args.url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    print(f"HTTP {response.status_code}", file=sys.stderr)
    if args.quiet:
        return 0 if response.ok else 1
    try:
        print(json.dumps(response.json(), indent=1)[:12000])
    except ValueError:
        print(response.text[:4000])
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
