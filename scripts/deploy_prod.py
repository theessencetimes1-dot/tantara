#!/usr/bin/env python3
"""Deploy TANTRA production to Cloud Run and Firebase Hosting.

Nothing here is destructive to the k8s QA stack: the images go to Artifact
Registry under their own tags, the Cloud Run services have their own names, and
the Firebase site is a new one. The operator's credential file supplies the
values; no secret is printed.

    backend/.venv/bin/python scripts/deploy_prod.py push      # images -> Artifact Registry
    backend/.venv/bin/python scripts/deploy_prod.py cloudrun  # create/update both services
    backend/.venv/bin/python scripts/deploy_prod.py hosting   # Firebase Hosting config
    backend/.venv/bin/python scripts/deploy_prod.py status    # what is live now

Run the subcommands in that order; ``all`` runs them in sequence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import requests  # noqa: E402

from gcloud_api import access_token  # noqa: E402
from prod_env import (  # noqa: E402
    BACKEND_SERVICE,
    GCP_PROJECT,
    REGION,
    SITE_ID,
    backend_env,
    creds,
)

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
KEY_FILE = os.environ.get("TANTARA_GSA_KEY", "sensitive/gcp-admin.json")
RUN_API = "https://run.googleapis.com/v2/projects"
HOSTING_API = f"https://firebasehosting.googleapis.com/v1beta1/projects/{GCP_PROJECT}"
BACKEND_IMAGE = f"{REGION}-docker.pkg.dev/{GCP_PROJECT}/tantara/tantara-api"
FRONTEND_IMAGE = f"{REGION}-docker.pkg.dev/{GCP_PROJECT}/tantara/tantara-web"
LOCAL_BACKEND = os.environ.get("TANTARA_LOCAL_BACKEND_IMAGE", "localhost/tantara-backend-prod:prod-20261030-1")
LOCAL_FRONTEND = os.environ.get("TANTARA_LOCAL_FRONTEND_IMAGE", "localhost/tantara-frontend-prod:prod-20261030-1")


def token() -> str:
    return access_token(KEY_FILE, SCOPE)


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def get_headers() -> dict[str, str]:
    # The v2 endpoints reject a JSON content-type on a bodiless GET.
    return {"Authorization": f"Bearer {token()}"}


def run_base() -> str:
    return f"{RUN_API}/{GCP_PROJECT}/locations/{REGION}/services"


def images(tag: str) -> list[str]:
    return [f"{BACKEND_IMAGE}:{tag}", f"{FRONTEND_IMAGE}:{tag}"]


def push(tag: str, only: str = "all") -> int:
    registry = f"{REGION}-docker.pkg.dev"
    with open(KEY_FILE) as handle:
        key = json.dumps(json.load(handle), separators=(",", ":"))
    login = subprocess.run(
        ["podman", "login", "-u", "_json_key", "--password-stdin", registry],
        input=key.encode(),
        capture_output=True,
        text=False,
    )
    if login.returncode != 0:
        print(login.stderr.decode()[:300])
        return 1
    print(f"logged in to {registry}")
    pairs = [(LOCAL_BACKEND, images(tag)[0]), (LOCAL_FRONTEND, images(tag)[1])]
    if only == "backend":
        pairs = pairs[:1]
    if only == "frontend":
        pairs = pairs[1:]
    for local, remote in pairs:
        for command in (["podman", "tag", local, remote], ["podman", "push", remote]):
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                print("FAILED:", " ".join(command), "\n", (result.stderr or result.stdout)[-500:])
                return 1
        print("pushed", remote)
    return 0


def env_pairs(env: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in sorted(env.items())]


def service_body(name: str, image: str, cpu: str, memory: str, port: int, env: dict[str, str], max_scale: str) -> dict:
    """Cloud Run v2 service body: one instance maximum, and it may idle to zero."""
    return {
        "labels": {"tantara": "production"},
        "description": "Tantra production workspace (Firebase Hosting + Supabase + Claude)",
        "launchStage": "GA",
        "template": {
            "labels": {"tantara": "production"},
            # Cold start is the accepted cost of an idle workspace: exactly one
            # instance maximum, and none while nobody is asking.
            "scaling": {"minInstanceCount": 0, "maxInstanceCount": int(max_scale)},
            "maxInstanceRequestConcurrency": 80,
            "timeout": "60s",
            "containers": [
                {
                    "image": image,
                    "name": name,
                    # Cloud Run injects PORT=8010 and routes there; both images listen on 8010.
                    "env": env_pairs(env),
                    "resources": {"limits": {"cpu": cpu, "memory": memory}, "cpuIdle": True},
                }
            ],
        },
        "traffic": [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}],
    }


def cloudrun(tag: str, api_uri: str = "", only: str = "all") -> int:
    c = creds()
    h = headers()
    base = run_base()
    pairs = [
        (BACKEND_SERVICE, service_body(BACKEND_SERVICE, f"{BACKEND_IMAGE}:{tag}", "4", "8Gi", 8010, backend_env(c, api_uri), "1")),
        (
            "tantara-web",
            service_body(
                "tantara-web",
                f"{FRONTEND_IMAGE}:{tag}",
                "1",
                "512Mi",
                3000,
                {"NODE_ENV": "production", "NEXT_TELEMETRY_DISABLED": "1"},
                "3",
            ),
        ),
    ]
    if only == "backend":
        pairs = pairs[:1]
    if only == "frontend":
        pairs = pairs[1:]
    for name, body in pairs:
        create = requests.post(base, headers=h, json=body, params={"serviceId": name}, timeout=240)
        if create.status_code == 409:
            create = requests.put(f"{base}/{name}", headers=h, json={**body, "name": f"{base}/{name}"}, timeout=240)
        payload = create.json() if "json" in create.headers.get("content-type", "") else {"raw": create.text[:300]}
        print(name, create.status_code, payload.get("uri") or payload.get("error") or str(payload)[:300])
        if create.status_code >= 400:
            return 1
        operation = payload.get("name")
        if operation:
            # Wait for the revision to become ready before reporting the URL.
            for _ in range(40):
                poll = requests.get(f"https://run.googleapis.com/v2/{operation}", headers=get_headers(), timeout=60)
                data = poll.json() if poll.ok else {}
                if data.get("done"):
                    print(f"  operation done: {json.dumps(data.get('response', {}))[:160]}")
                    break
                time.sleep(5)
        policy = requests.post(
            f"{base}/{name}:setIamPolicy",
            headers=h,
            json={"policy": {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}},
            timeout=120,
        )
        print(f"  invoker: {policy.status_code} {policy.text[:120] if policy.status_code >= 400 else 'public'}")
        service = requests.get(f"{base}/{name}", headers=get_headers(), timeout=120)
        if service.ok:
            print(f"  uri: {service.json().get('uri')}")
    return 0


def hosting() -> int:
    """Release the Hosting configuration in ``firebase.json``.

    The REST API can create and finalise a version, but it does not expose the
    release call that promotes a version to live traffic — the site kept
    serving "Site Not Found" after a REST-only deploy. firebase-tools does the
    upload, finalise and release in one pass, and it authenticates from
    $GOOGLE_APPLICATION_CREDENTIALS, so the service account is used without any
    interactive login.
    """
    env = dict(os.environ)
    env.setdefault("GOOGLE_APPLICATION_CREDENTIALS", KEY_FILE)
    result = subprocess.run(
        ["firebase", "deploy", "--only", "hosting", "--project", GCP_PROJECT, "--non-interactive"],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    print("\n".join(lines[-10:]))
    print(f"  site: https://{SITE_ID}.web.app")
    return result.returncode


def status() -> int:
    h = get_headers()
    services = requests.get(run_base(), headers=h, timeout=120).json()
    for item in services.get("services", []):
        uid = item.get("name", "").split("/")[-1]
        print(f"{uid:26} {item.get('uri','')} scaling={item.get('template',{}).get('template',{}).get('maxInstanceCount')}")
    sites = requests.get(f"{HOSTING_API}/sites", headers=h, timeout=120).json()
    for site in sites.get("sites", []):
        print("site:", site.get("siteId"), site.get("defaultUrl"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["push", "cloudrun", "hosting", "status", "all"])
    parser.add_argument("--tag", default=os.environ.get("TANTARA_PROD_TAG", "prod-20261030-1"))
    parser.add_argument("--only", choices=["all", "backend", "frontend"], default="all")
    args = parser.parse_args()
    if args.command == "push":
        return push(args.tag, args.only)
    if args.command == "cloudrun":
        return cloudrun(args.tag, only=args.only)
    if args.command == "hosting":
        return hosting()
    if args.command == "status":
        return status()
    for step in (push, lambda: cloudrun(args.tag), hosting, status):
        code = step(args.tag) if step is push else step()
        if code:
            return code
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
