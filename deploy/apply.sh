#!/usr/bin/env bash
# Apply the TANTRA workspace to the k3s cluster.
#
# Usage: deploy/apply.sh [--tag TAG] [--seed] [--dns]
#   --seed  run the demo workspace loader Job after the backend is ready
#   --dns   create/update the public Cloudflare DNS record for the tunnel
#
# Secrets are read from the local credentials file by deploy/render-config.py and
# pushed as Kubernetes Secrets; they are never written into Git or into an image.
set -euo pipefail

REGISTRY="192.168.0.100:5000"
NAMESPACE="tantara"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTHFILE="${TANTARA_REGISTRY_AUTHFILE:-$HOME/.config/tantara/registry-auth.json}"
LAST_TAG_FILE="$REPO_ROOT/deploy/.last-tag"

export KUBECONFIG="${KUBECONFIG:-$REPO_ROOT/sensitive/kubeconfig}"

TAG=""
SEED=0
DNS=0
HOSTNAME_OVERRIDE="${TANTARA_HOSTNAME:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --seed) SEED=1; shift ;;
    --dns) DNS=1; shift ;;
    --hostname) HOSTNAME_OVERRIDE="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TAG" ]; then
  if [ -f "$LAST_TAG_FILE" ]; then
    TAG="$(cat "$LAST_TAG_FILE")"
  else
    echo "no image tag given and deploy/.last-tag is missing; run deploy/build.sh first" >&2
    exit 1
  fi
fi

WORKDIR="$(mktemp -d -t tantara-deploy.XXXXXX)"
chmod 700 "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> rendering deployment inputs (tag $TAG)"
if [ -n "$HOSTNAME_OVERRIDE" ]; then
  python3 "$REPO_ROOT/deploy/render-config.py" --out "$WORKDIR" --hostname "$HOSTNAME_OVERRIDE"
else
  python3 "$REPO_ROOT/deploy/render-config.py" --out "$WORKDIR"
fi

kubectl apply -f "$REPO_ROOT/deploy/k8s/00-namespace.yaml"

echo "==> secrets"
kubectl -n "$NAMESPACE" create secret generic tantara-secrets \
  --from-env-file="$WORKDIR/secrets.env" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" create secret generic tantara-registry \
  --from-file=".dockerconfigjson=$AUTHFILE" \
  --type=kubernetes.io/dockerconfigjson \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" create secret generic tantara-cloudflared \
  --from-file="config.yml=$WORKDIR/config.yml" \
  --from-file="credentials.json=$WORKDIR/credentials.json" \
  --dry-run=client -o yaml | kubectl apply -f -

apply_manifest() {
  local file="$1" rendered
  rendered="$WORKDIR/$(basename "$file")"
  sed -E "s|(${REGISTRY}/tantara-[a-z]+):pending|\1:${TAG}|g" "$file" > "$rendered"
  kubectl apply -f "$rendered"
}

echo "==> workloads"
for file in 10-backend.yaml 20-frontend.yaml 30-ingress.yaml 40-tunnel.yaml; do
  apply_manifest "$REPO_ROOT/deploy/k8s/$file"
done

echo "==> waiting for rollouts"
kubectl -n "$NAMESPACE" rollout status deployment/tantara-backend --timeout=420s
kubectl -n "$NAMESPACE" rollout status deployment/tantara-frontend --timeout=300s
# The tunnel is the public door, not the app: if it cannot start (revoked token, the
# hostname no longer assigned to this tunnel) the workspace is still reachable through
# the LAN ingress, so warn instead of failing the apply.
kubectl -n "$NAMESPACE" rollout status deployment/tantara-tunnel --timeout=300s \
  || echo "WARNING: tantara-tunnel is not ready — run: kubectl -n $NAMESPACE logs deploy/tantara-tunnel"

if [ "$SEED" = "1" ]; then
  echo "==> demo workspace loader"
  kubectl -n "$NAMESPACE" delete job tantara-seed-demo --ignore-not-found --wait=true
  apply_manifest "$REPO_ROOT/deploy/k8s/50-seed-job.yaml"
  kubectl -n "$NAMESPACE" wait --for=condition=complete job/tantara-seed-demo --timeout=900s
fi

if [ "$DNS" = "1" ]; then
  echo "==> public DNS"
  python3 "$REPO_ROOT/deploy/set-dns.py" --credentials-dir "$WORKDIR"
fi

echo "==> state"
kubectl -n "$NAMESPACE" get deploy,job,ingress -o wide
kubectl -n "$NAMESPACE" get pods -o wide
