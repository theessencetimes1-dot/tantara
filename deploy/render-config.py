#!/usr/bin/env python3
"""Render the Kubernetes Secret inputs for the TANTRA deployment.

Local operator tool: it reads the authorized local credentials file and writes
rendered files into a private temporary directory chosen by deploy/apply.sh.
Never run it in CI and never commit or print what it produces.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from pathlib import Path

CREDENTIALS = Path("/home/kahitoz/projects/tantara/sensitive/creds.yaml")
PASSWORD_FILE = Path.home() / ".config" / "tantara" / "tantara-admin-password"


def read_sections(path: Path) -> dict[str, dict[str, str]]:
    """Parse the credentials file leniently.

    The file is hand-maintained and not strictly valid YAML (a value can follow the
    colon without a space), so a line-based parser is used instead of yaml.safe_load.
    Values are never echoed.
    """
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if indent == 0:
            if value:
                sections[key] = {"value": value}
                current = None
            else:
                sections[key] = {}
                current = key
        elif current is not None:
            sections[current][key] = value
    return sections


def tunnel_credentials(token: str) -> dict[str, str]:
    """Decode the tunnel token: base64 of the connector credentials JSON.

    cloudflared writes short keys (a/s/t) into the token and long keys into the
    credentials file, so both spellings are accepted.
    """
    padding = "=" * (-len(token) % 4)
    payload = json.loads(base64.b64decode(token + padding).decode("utf-8"))
    aliases = {
        "AccountTag": ("a", "AccountTag"),
        "TunnelSecret": ("s", "TunnelSecret"),
        "TunnelID": ("t", "TunnelID"),
    }
    credentials: dict[str, str] = {}
    for field, names in aliases.items():
        value = next((payload[name] for name in names if payload.get(name)), None)
        if not value:
            raise SystemExit(f"tunnel token is missing {field}")
        credentials[field] = value
    return credentials


def admin_password() -> str:
    if PASSWORD_FILE.is_file():
        password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
        if password:
            return password
    password = secrets.token_urlsafe(24)
    PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    PASSWORD_FILE.write_text(password + "\n", encoding="utf-8")
    PASSWORD_FILE.chmod(0o600)
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="private output directory")
    parser.add_argument("--hostname", help="override the public hostname")
    parser.add_argument("--print-password", action="store_true", help="print the admin password")
    args = parser.parse_args()

    if not CREDENTIALS.is_file():
        raise SystemExit(f"credentials file not found: {CREDENTIALS}")
    sections = read_sections(CREDENTIALS)
    postgres = sections.get("postgres") or {}
    minio = sections.get("minio") or {}
    cloudflare = sections.get("cloudflare_tunnel") or {}
    required = {
        "postgres": ["host", "port", "database", "user", "password"],
        "minio": ["endpoint", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"],
        "cloudflare_tunnel": ["tunnel_token", "domain"],
    }
    missing = [
        f"{section}.{key}"
        for section, keys in required.items()
        for key in keys
        if not (sections.get(section) or {}).get(key)
    ]
    if missing:
        raise SystemExit("credentials file is missing: " + ", ".join(missing))

    # `subdomain` used to live in the credentials file; the Cloudflare side has since been
    # edited by hand (it now carries `path: /api`), so the public hostname is accepted from
    # --hostname as well. Without either there is nothing sensible to route the tunnel to.
    subdomain = cloudflare.get("subdomain") or cloudflare.get("hostname")
    if args.hostname:
        hostname = args.hostname
    elif subdomain:
        hostname = f"{subdomain}.{cloudflare['domain']}"
    else:
        raise SystemExit(
            "no public hostname: credentials file has no cloudflare_tunnel.subdomain, so pass "
            "--hostname <host>, e.g. --hostname tantra.theessencetimes.com"
        )
    out = args.out
    out.mkdir(parents=True, exist_ok=True, mode=0o700)

    database_url = (
        f"postgresql+psycopg://{postgres['user']}:{postgres['password']}"
        f"@{postgres['host']}:{postgres['port']}/{postgres['database']}"
    )
    # The owner's choice on 8 Nov: the LAN model host (192.168.0.101) is down, so the
    # workspace runs on the Anthropic API like production does. The backend only reads
    # `ANTHROPIC_API_KEY` + `CLAUDE_MODEL` and uses the SDK's own endpoint, so
    # `CLAUDE_API_URL` in the credentials file is deliberately not wired here — an
    # OpenAI-compatible proxy URL would be silently ignored.
    claude = sections.get("CLAUDE_PROD") or {}
    env_lines = [
        f"DATABASE_URL={database_url}",
        f"S3_ACCESS_KEY={minio['MINIO_ACCESS_KEY']}",
        f"S3_SECRET_KEY={minio['MINIO_SECRET_KEY']}",
        f"TANTARA_ADMIN_PASSWORD={admin_password()}",
    ]
    if claude.get("CLAUDE_API_KEY"):
        env_lines += [
            f"ANTHROPIC_API_KEY={claude['CLAUDE_API_KEY']}",
            f"CLAUDE_MODEL={claude.get('CLAUDE_MODEL') or 'claude-haiku-5-5'}",
        ]
    env_path = out / "secrets.env"
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    env_path.chmod(0o600)

    tunnel = tunnel_credentials(cloudflare["tunnel_token"])
    file_tunnel_id = cloudflare.get("tunnel_id") or ""
    if file_tunnel_id and file_tunnel_id != tunnel["TunnelID"]:
        print(
            f"note: credentials file tunnel_id {file_tunnel_id} does not match the token "
            f"TunnelID {tunnel['TunnelID']}; using the token value",
            file=sys.stderr,
        )
    (out / "credentials.json").write_text(json.dumps(tunnel) + "\n", encoding="utf-8")
    (out / "credentials.json").chmod(0o600)

    backend_service = "http://tantara-backend.tantara.svc.cluster.local:8010"
    frontend_service = "http://tantara-frontend.tantara.svc.cluster.local:3000"
    # cloudflared matches paths with a regular expression in the `path:` field.
    # A path appended to `hostname:` parses but never matches, so the whole site
    # would fall through to the catch-all rule.
    backend_paths = [r"^/api/v1(/.*)?$", r"^/(?:health|readyz)$"]
    lines = [
        f"tunnel: {tunnel['TunnelID']}",
        "credentials-file: /etc/cloudflared/credentials.json",
        "ingress:",
    ]
    for pattern in backend_paths:
        lines += [
            f"  - hostname: {hostname}",
            f"    path: {pattern}",
            f"    service: {backend_service}",
        ]
    lines += [
        f"  - hostname: {hostname}",
        f"    service: {frontend_service}",
        "  - service: http_status:404",
        "",
    ]
    config_path = out / "config.yml"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    config_path.chmod(0o600)

    print(f"tunnel id: {tunnel['TunnelID']}")
    print(f"public hostname: {hostname}")
    print(f"postgres: {postgres['host']}:{postgres['port']}/{postgres['database']}")
    print(f"minio endpoint: {minio['endpoint']}")
    if args.print_password:
        print(f"admin password file: {PASSWORD_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
