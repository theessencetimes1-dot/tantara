#!/usr/bin/env python3
"""Credential and environment assembly for the TANTRA production deployment.

Production runs on Firebase Hosting (frontend) + Cloud Run (backend) +
Supabase (Postgres + Storage) + Claude. The k8s workspace stack is a separate,
untouched QA deployment, so this module only ever assembles the *production*
environment.

Secrets are read from ``sensitive/creds.yaml`` by the local orchestrator and
passed to Google Cloud / the deploy scripts in memory. Nothing here prints a
secret: ``mask()`` is applied to every value the tooling echoes, and the only
exported artifact is the Cloud Run env JSON, which Google stores server-side.

    backend/.venv/bin/python scripts/prod_env.py env        # masked summary
    backend/.venv/bin/python scripts/prod_env.py env --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

CREDS_PATH = os.environ.get("TANTARA_CREDS", "sensitive/creds.yaml")
SITE_ID = os.environ.get("TANTARA_FIREBASE_SITE", "tantara-prod")
GCP_PROJECT = os.environ.get("TANTARA_GCP_PROJECT", "tantra-513216")
# Hosting rewrites to Cloud Run only work inside one project, and the existing
# the-essence-times Firebase project cannot enable Cloud Run with the supplied
# credentials, so Firebase was enabled on the billing-enabled GCP project above
# and the site was created there: https://tantara-prod.web.app
FIREBASE_PROJECT = os.environ.get("TANTARA_FIREBASE_PROJECT", GCP_PROJECT)
REGION = os.environ.get("TANTARA_REGION", "asia-south1")
AR_REPO = os.environ.get("TANTARA_AR_REPO", "tantara")
BACKEND_SERVICE = "tantara-api"
FRONTEND_ORIGIN = f"https://{SITE_ID}.web.app"
STORAGE_BUCKET = os.environ.get("TANTARA_STORAGE_BUCKET", "tantara-documents")
PRODUCTION_PASSWORD_FILE = os.path.expanduser("~/.config/tantara/tantara-prod-password")

_SECRET_KEYS = re.compile(r"(key|token|password|secret|connection|passwd)", re.I)


def creds(path: str = CREDS_PATH) -> dict[str, str]:
    """Flat ``SECTION.KEY`` map of the workspace credential file.

    ``sensitive/creds.yaml`` is hand-edited and not strict YAML (an unquoted
    value contains ``: ``), so it is parsed line-wise instead of with a parser.
    """
    out: dict[str, str] = {}
    section = None
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if top and not top.group(2).strip():
            section = top.group(1)
            continue
        if top and section is None:
            section = top.group(1)
            continue
        nested = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\S.*?)\s*$", line)
        if nested and section:
            out[f"{section}.{nested.group(1).upper()}"] = nested.group(2)
    return out


def mask(value: str | None) -> str:
    if not value:
        return "«unset»"
    if len(value) <= 10:
        return "«set»"
    if "@" in value:  # a connection string: keep only the host
        host = re.search(r"@([^/?]+)", value)
        return f"«connection → {host.group(1) if host else '?'}»"
    return f"{value[:4]}…«len={len(value)}»"


def production_database_url(c: dict[str, str]) -> str:
    """Session-pooler (Supavisor) DSN instead of the direct Postgres host.

    Supabase provisions its Postgres in an IPv6-only subnet: ``db.<ref>.supabase.co``
    answers AAAA only, so a Cloud Run container (IPv4 egress) can never reach it.
    The session pooler in the project's own region answers IPv4 and holds one
    real connection per client, which is what a single-instance backend wants.
    """
    direct = c["supabase_prod.CONNECTION_STRING"]
    match = re.match(
        r"^(?P<scheme>postgresql(?:\+psycopg2?)?)://(?P<user>[^:]+):(?P<pw>[^@]*)@(?P<host>[^:/]+):(?P<port>\d+)/(?P<db>[^?]+)",
        direct,
    )
    if not match:
        return direct.replace("postgresql://", "postgresql+psycopg://", 1)
    ref = re.sub(r"^db\.", "", match["host"]).split(".")[0]
    region = os.environ.get("TANTARA_SUPABASE_REGION", "ap-south-1")
    user = f"{match['user']}.{ref}" if match["host"].startswith("db.") else match["user"]
    from urllib.parse import quote, unquote

    # The dashboard hands out a percent-encoded password; decode before re-encoding
    # so a ``%40`` in the secret survives exactly once.
    password = quote(unquote(match["pw"]), safe="")

    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{password}"
        f"@aws-0-{region}.pooler.supabase.com:5432/{match['db']}?sslmode=require"
    )


def claude_model(c: dict[str, str]) -> str:
    """The Anthropic model to run: operator override, then creds, then a known-good default.

    `claude-sonnet-4-20250514` is retired upstream and answers 404, which is why the
    model name is read from `CLAUDE_PROD.CLAUDE_MODEL` instead of hardcoded.
    """
    return (
        os.environ.get("TANTARA_CLAUDE_MODEL")
        or c.get("CLAUDE_PROD.CLAUDE_MODEL")
        or "claude-haiku-5-5"
    )


def backend_env(c: dict[str, str], api_uri: str = "") -> dict[str, str]:
    """Environment for the Cloud Run backend container. Values, not names."""
    anthropic_key = c.get("CLAUDE_PROD.CLAUDE_API_KEY", "")
    env = {
        "DATABASE_URL": production_database_url(c),
        "OBJECT_STORAGE": "supabase",
        "SUPABASE_URL": c["supabase_prod.SUPABASE_URL"],
        "SUPABASE_SERVICE_ROLE_KEY": c["supabase_prod.SUPABASE_SECRET_KEY"],
        "SUPABASE_STORAGE_BUCKET": STORAGE_BUCKET,
        "VECTOR_BACKEND": "postgres",
        "AI_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": anthropic_key,
        "CLAUDE_MODEL": claude_model(c),
        "ENABLE_CLOUD_PROVIDERS": "true",
        "EMBEDDING_PROVIDER": "fastembed",
        "TANTARA_WORKSPACE_TIME_ZONE": "Asia/Kolkata",
        "DATA_DIR": "/tmp/tantara",
        "CORS_ORIGINS": ",".join([FRONTEND_ORIGIN, f"https://{SITE_ID}.firebaseapp.com"]),
        "DB_POOL_SIZE": "5",
        "DB_POOL_MAX_OVERFLOW": "5",
        "TANTARA_ADMIN_PASSWORD": production_password(),
    }
    if api_uri:
        env["PUBLIC_API_ORIGIN"] = api_uri
    return env


def frontend_build_args(c: dict[str, str], api_uri: str) -> dict[str, str]:
    """Build-time arguments for the static frontend export."""
    if not api_uri:
        raise SystemExit("a Cloud Run API URL is required to build the frontend")
    return {
        "NEXT_PUBLIC_API_BASE_URL": api_uri,
        "NEXT_PUBLIC_WORKSPACE_TIME_ZONE": "Asia/Kolkata",
        "TANTARA_STATIC_EXPORT": "1",
    }


def production_password() -> str:
    """Stable strong password for the production admin/demo account.

    Generated once and kept in the operator config directory, never in the
    repository and never printed.
    """
    if os.path.exists(PRODUCTION_PASSWORD_FILE):
        return open(PRODUCTION_PASSWORD_FILE, encoding="utf-8").read().strip()
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    value = "Tantra-Prod-" + "".join(secrets.choice(alphabet) for _ in range(18)) + "!"
    os.makedirs(os.path.dirname(PRODUCTION_PASSWORD_FILE), exist_ok=True)
    fd = os.open(PRODUCTION_PASSWORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("what", choices=["env", "targets"], nargs="?", default="env")
    parser.add_argument("--json", help="write the backend env to this file (values, for the deploy)")
    parser.add_argument(
        "--env-file",
        help="write KEY=VALUE lines (mode 600) for podman --env-file; delete it when done",
    )
    parser.add_argument("--api-uri", default="", help="Cloud Run URL to bake into CORS/env")
    args = parser.parse_args()

    c = creds()
    if args.what == "targets":
        print(json.dumps({
            "gcp_project": GCP_PROJECT,
            "region": REGION,
            "artifact_registry": f"{REGION}-docker.pkg.dev/{GCP_PROJECT}/{AR_REPO}",
            "cloud_run_service": BACKEND_SERVICE,
            "firebase_project": FIREBASE_PROJECT,
            "firebase_site": SITE_ID,
            "frontend_origin": FRONTEND_ORIGIN,
            "supabase_ref": re.sub(r"^https://([^.]+)\..*$", r"\1", c["supabase_prod.SUPABASE_URL"]),
            "storage_bucket": STORAGE_BUCKET,
            "claude_model": claude_model(c),
        }, indent=1))
        return 0

    env = backend_env(c, args.api_uri)
    if args.env_file:
        # The corpus owner's password is passed only to the one-off import
        # container; the Cloud Run service never carries it.
        env["TANTARA_CORPUS_PASSWORD"] = production_password()
        fd = os.open(args.env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for name, value in env.items():
                if "\n" in value:
                    raise SystemExit(f"{name} contains a newline and cannot go in an env file")
                handle.write(f"{name}={value}\n")
        print(f"wrote {len(env)} variables to {args.env_file} (mode 600)")
        return 0
    if args.json:
        fd = os.open(args.json, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(env, handle)
        print(f"wrote {len(env)} variables to {args.json} (mode 600)")
        return 0
    for name in sorted(env):
        print(f"{name} = {env[name] if name in {'VECTOR_BACKEND','OBJECT_STORAGE','AI_PROVIDER','EMBEDDING_PROVIDER','ENABLE_CLOUD_PROVIDERS','CLAUDE_MODEL','TANTARA_WORKSPACE_TIME_ZONE','DATA_DIR','CORS_ORIGINS','DB_POOL_SIZE','DB_POOL_MAX_OVERFLOW','SUPABASE_STORAGE_BUCKET'} else mask(env[name])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
