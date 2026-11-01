#!/usr/bin/env python3
"""Render the TANTRA production deployment + runtime flow as a single PNG.

Drawn with Pillow only (this workstation has no graphviz/matplotlib). Every fact
comes from the repository: deploy/Containerfile.backend, deploy/Containerfile.frontend,
firebase.json, scripts/deploy_prod.py, scripts/prod_env.py and backend/app.
Regenerate after any change to those files:

    backend/.venv/bin/python scripts/render_prod_diagram.py
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

F_TITLE = ImageFont.truetype(BOLD, 42)
F_BAND = ImageFont.truetype(BOLD, 26)
F_BOX = ImageFont.truetype(BOLD, 21)
F_BODY = ImageFont.truetype(REG, 17)
F_LABEL = ImageFont.truetype(BOLD, 17)
F_FOOT = ImageFont.truetype(REG, 16)

INK = (30, 34, 40)
MUTED = (95, 103, 115)
WHITE = (255, 255, 255)
BUILD, BUILD_E = (232, 240, 251), (74, 112, 172)
DELIV, DELIV_E = (238, 233, 250), (116, 96, 176)
RUNT, RUNT_E = (232, 246, 237), (62, 130, 92)
OPS, OPS_E = (253, 242, 228), (176, 128, 58)
EXT, EXT_E = (250, 236, 236), (166, 82, 82)
NOTE, NOTE_E = (253, 247, 234), (172, 134, 60)

WIDTH = 2920
MARGIN = 46
LINE = 26

_measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def wrap(text: str, font, max_px: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if _measure.textlength(trial, font=font) <= max_px:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Diagram:
    def __init__(self) -> None:
        self.boxes: dict[str, dict] = {}
        self.bands: list[dict] = []
        self.arrows: list[dict] = []

    def box(self, bid, band, x, w, title, lines, fill, edge, dy=0):
        rows = [piece for line in lines for piece in wrap(line, F_BODY, w - 34)]
        self.boxes[bid] = dict(band=band, x=x, w=w, dy=dy, h=52 + LINE * len(rows) + 14,
                               title=title, rows=rows, fill=fill, edge=edge)

    def band(self, name, label, fill, edge, align="left"):
        heights = [b["dy"] + b["h"] for b in self.boxes.values() if b["band"] == name]
        self.bands.append(dict(name=name, label=label, fill=fill, edge=edge, align=align,
                               h=max(heights) + 92))

    def arrow(self, a, b, label="", dashed=False, color=(72, 82, 96), frm="r", to="l", elbow=0):
        self.arrows.append(dict(a=a, b=b, label=label, dashed=dashed, color=color, frm=frm, to=to, elbow=elbow))

    def layout(self) -> None:
        y = 156
        for band in self.bands:
            band["y"] = y
            for box in (b for b in self.boxes.values() if b["band"] == band["name"]):
                box["y"] = y + 80 + box["dy"]
            y += band["h"] + 38
        self.height = y + 110

    # ---------------------------------------------------------------- painting
    def render(self, title, subtitle, out):
        self.layout()
        img = Image.new("RGB", (WIDTH, self.height), WHITE)
        d = ImageDraw.Draw(img)
        d.text((MARGIN, 40), title, font=F_TITLE, fill=INK)
        d.text((MARGIN, 100), subtitle, font=F_BODY, fill=MUTED)
        for band in self.bands:
            d.rounded_rectangle([MARGIN - 14, band["y"] - 36, WIDTH - MARGIN + 14, band["y"] + band["h"] - 16],
                                radius=18, fill=band["fill"], outline=band["edge"], width=3)
            if band.get("align") == "right":
                tw = d.textlength(band["label"], font=F_BAND)
                d.text((WIDTH - MARGIN - 20 - tw, band["y"] - 26), band["label"], font=F_BAND, fill=band["edge"])
            else:
                d.text((MARGIN + 6, band["y"] - 26), band["label"], font=F_BAND, fill=band["edge"])
        for box in self.boxes.values():
            x, y, w, h = box["x"], box["y"], box["w"], box["h"]
            d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=WHITE, outline=box["edge"], width=3)
            d.rounded_rectangle([x, y, x + w, y + 46], radius=14, fill=box["edge"])
            d.rectangle([x, y + 30, x + w, y + 46], fill=box["edge"])
            d.text((x + 16, y + 12), box["title"], font=F_BOX, fill=WHITE)
            ty = y + 60
            for row in box["rows"]:
                d.text((x + 17, ty), row, font=F_BODY, fill=INK)
                ty += LINE
        for arrow in self.arrows:
            self.paint_arrow(d, arrow)
        d.text((MARGIN, self.height - 62),
               "Read from deploy/Containerfile.backend, deploy/Containerfile.frontend, firebase.json, "
               "scripts/deploy_prod.py, scripts/prod_env.py and backend/app — regenerate with "
               "scripts/render_prod_diagram.py. No secret values appear in this diagram.",
               font=F_FOOT, fill=MUTED)
        img.save(out)
        print(out, img.size)

    @staticmethod
    def anchor(box, side):
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        return {"l": (x, y + h // 2), "r": (x + w, y + h // 2),
                "t": (x + w // 2, y), "b": (x + w // 2, y + h)}[side]

    def dash(self, d, p, q, color, inset=14):
        total = math.hypot(q[0] - p[0], q[1] - p[1])
        if total == 0:
            return
        stop = max(total - inset, 0)
        travelled = 0.0
        while travelled < stop:
            seg = min(10, stop - travelled)
            a = travelled / total
            b = (travelled + seg) / total
            d.line([p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a,
                    p[0] + (q[0] - p[0]) * b, p[1] + (q[1] - p[1]) * b], fill=color, width=3)
            travelled += 20

    def head(self, d, frm, to, color):
        angle = math.atan2(to[1] - frm[1], to[0] - frm[0])
        for spread in (2.6, -2.6):
            d.line([to[0], to[1], to[0] - 17 * math.cos(angle - spread), to[1] - 17 * math.sin(angle - spread)],
                   fill=color, width=4)

    def label(self, d, center, text, color):
        if not text:
            return
        lines = wrap(text, F_LABEL, 260)
        tw = max(d.textlength(t, font=F_LABEL) for t in lines)
        th = 21 * len(lines)
        cx, cy = center
        d.rounded_rectangle([cx - tw / 2 - 8, cy - th / 2 - 5, cx + tw / 2 + 8, cy + th / 2 + 5],
                            radius=8, fill=WHITE, outline=color, width=2)
        ty = cy - th / 2
        for line in lines:
            d.text((cx - d.textlength(line, font=F_LABEL) / 2, ty), line, font=F_LABEL, fill=color)
            ty += 21

    def paint_arrow(self, d, arrow):
        a, b = self.boxes[arrow["a"]], self.boxes[arrow["b"]]
        p, q = self.anchor(a, arrow["frm"]), self.anchor(b, arrow["to"])
        color = arrow["color"]
        pts = [p, q]
        if arrow["elbow"]:
            mid_y = p[1] + arrow["elbow"]
            pts = [p, (p[0], mid_y), (q[0], mid_y), q]
        last = pts[-2]
        ux, uy = q[0] - last[0], q[1] - last[1]
        ulen = math.hypot(ux, uy)
        if ulen:
            pts[-1] = (q[0] - 17 * ux / ulen, q[1] - 17 * uy / ulen)
        for seg_from, seg_to in zip(pts, pts[1:]):
            if arrow["dashed"]:
                self.dash(d, seg_from, seg_to, color, inset=0)
            else:
                d.line([seg_from, seg_to], fill=color, width=4)
        self.head(d, pts[-2], pts[-1], color)
        mid_a, mid_b = pts[len(pts) // 2 - 1], pts[len(pts) // 2] if len(pts) == 2 else pts[2]
        center = ((mid_a[0] + mid_b[0]) / 2, (mid_a[1] + mid_b[1]) / 2)
        self.label(d, center, arrow["label"], color)


def main() -> None:
    dg = Diagram()

    # 1 ── build ───────────────────────────────────────────────────────────────
    dg.box("git", "build", 70, 420, "Source tree (git)", [
        "branch feat/postgres-minio-deploy",
        "backend/ FastAPI app + Alembic migrations",
        "frontend/ Next.js workspace app",
        "deploy/Containerfile.backend and Containerfile.frontend",
        "sensitive/ is never read by a cloud coding agent",
    ], WHITE, BUILD_E)
    dg.box("gates", "build", 640, 420, "Gates before any image", [
        "pytest: 172 passed, 5 skipped",
        "ruff check backend/app",
        "pnpm lint, pnpm typecheck, pnpm build",
        "secret scan of the whole diff",
    ], WHITE, BUILD_E)
    dg.box("build", "build", 1210, 500, "podman build (context = repo root)", [
        "rm -rf frontend/.next first; one tag for both images:",
        "prod-YYYYMMDD-HHMM",
        "backend: python:3.12-slim, uvicorn :8010, --workers 1,",
        "FastEmbed + RapidOCR caches baked in, HF_HUB_OFFLINE=1, uid 1000",
        "frontend: node:24-slim multi-stage, pnpm 12.5.1,",
        "next build (output standalone) -> node server.js, uid 1001",
    ], WHITE, BUILD_E)
    dg.box("deploy", "build", 1860, 460, "scripts/deploy_prod.py", [
        "orchestrator-only tooling (never given to a coding agent)",
        "push      -> podman push to Artifact Registry",
        "cloudrun  -> Cloud Run v2 create / PATCH",
        "hosting   -> firebase deploy --only hosting",
        "status    -> live image tag and traffic check",
    ], WHITE, BUILD_E)
    dg.box("creds", "build", 2470, 400, "Credential boundary", [
        "sensitive/creds.yaml +",
        "~/.config/tantara/tantara-prod-password",
        "scripts/prod_env.py injects env NAMES into the revision:",
        "DATABASE_URL, OBJECT_STORAGE=supabase, SUPABASE_URL,",
        "SERVICE_ROLE_KEY, STORAGE_BUCKET, VECTOR_BACKEND=postgres,",
        "AI_PROVIDER=anthropic, ANTHROPIC_API_KEY, CLAUDE_MODEL,",
        "EMBEDDING_PROVIDER=fastembed, DATA_DIR=/tmp/tantara,",
        "CORS_ORIGINS, DB_POOL_SIZE, TANTARA_WORKSPACE_TIME_ZONE",
        "values are never printed, committed or sent to an agent",
    ], NOTE, NOTE_E)
    dg.band("build", "1  BUILD — orchestrator workstation (no cloud coding agent in this path)", BUILD, BUILD_E)

    # 2 ── delivery ────────────────────────────────────────────────────────────
    dg.box("ar", "delivery", 70, 560, "Artifact Registry (asia-south1)", [
        "asia-south1-docker.pkg.dev/tantra-513216/tantara",
        "tantara-api:prod-YYYYMMDD-HHMM    tantara-web:prod-YYYYMMDD-HHMM",
        "auth: OAuth2 token from the service-account key",
        "sensitive/gcp-admin.json (scope cloud-platform)",
    ], WHITE, DELIV_E)
    dg.box("runapi", "delivery", 780, 640, "Cloud Run Admin API v2", [
        "POST service -> 409 -> PATCH ?updateMask=template,traffic",
        "poll the returned operation until it completes",
        "the template MUST declare containers[].ports (8010 / 8080):",
        "without it a revision ends CONDITION_FAILED and traffic",
        "silently stays on the previous image",
        "traffic: LATEST 100%; label tantara=production",
    ], WHITE, DELIV_E)
    dg.box("hostapi", "delivery", 1570, 560, "Firebase Hosting release", [
        "site tantara-prod -> https://tantara-prod.web.app",
        "public: frontend/public, cleanUrls false",
        "a new version is released on every frontend change, or the",
        "previously released HTML keeps being served",
    ], WHITE, DELIV_E)
    dg.box("rules", "delivery", 2280, 590, "Rules that decide a real deploy", [
        "deploy the tag you just built — re-tagging an old image ships old code",
        "mtimes prove nothing: diff the deployed image against the tree",
        "(podman create + podman cp + diff)",
        "Cloud Run logs are not readable here (entries:read 404), so",
        "behaviour is proved from the API, the database and the browser",
    ], NOTE, NOTE_E)
    dg.band("delivery", "2  DELIVERY — Google Cloud, project tantra-513216, region asia-south1", DELIV, DELIV_E)

    # 3 ── runtime ─────────────────────────────────────────────────────────────
    dg.box("user", "runtime", 70, 300, "Users", [
        "browser: advocate,",
        "researcher, staff, admin",
        "session: JWT bearer from",
        "/api/v1/auth/login",
    ], WHITE, RUNT_E)
    dg.box("edge", "runtime", 520, 480, "Firebase Hosting edge", [
        "tantara-prod.web.app",
        "rewrites: /health, /api/v1/**, /ingest/** -> run:tantara-api;",
        "/** -> run:tantara-web",
        "headers: X-Frame-Options DENY, X-Content-Type-Options nosniff,",
        "Referrer-Policy strict-origin-when-cross-origin",
        "/_next/static immutable for 1 year; HTML max-age=0,",
        "s-maxage=60, must-revalidate",
    ], WHITE, RUNT_E)
    dg.box("web", "runtime", 1150, 520, "Cloud Run  tantara-web", [
        "image tantara-web:prod-...  node server.js",
        "containerPort 8080 (Cloud Run injects PORT)",
        "cpu 1, memory 512Mi, cpuIdle true",
        "min 0 / max 3 instances, concurrency 80, timeout 600s",
        "env: NODE_ENV=production, NEXT_TELEMETRY_DISABLED=1",
        "Next rewrite table proxies /api/v1/*, /api/v1/ingest/file",
        "and /health to the API origin (baked at build time)",
    ], WHITE, RUNT_E)
    dg.box("api", "runtime", 1820, 600, "Cloud Run  tantara-api", [
        "uvicorn app.main:app --port 8010 --workers 1 (one worker keeps",
        "the in-process ingestion lock and rate limiter exact)",
        "cpu 4, memory 8Gi, cpuIdle true, min 0 / max 1, concurrency 80,",
        "timeout 600s, DATA_DIR=/tmp/tantara (ephemeral)",
        "FastAPI routers, Pydantic v2, CORSMiddleware (CORS_ORIGINS)",
        "SQLAlchemy 2 + psycopg (pool 5 + 5); Alembic 0001 -> 0013",
        "ingestion: ThreadPoolExecutor(max_workers=2) plus",
        "ingestion_recovery_loop() started in lifespan; IngestionJob rows",
        "are claimed and swept so interrupted jobs resume",
        "retrieval: Postgres tsvector/GIN + pgvector + RRF fusion, only",
        "documents with status ready",
        "uploads: pypdf / pypdfium2, RapidOCR fallback, typed 4xx errors",
        "for unreadable files",
    ], WHITE, RUNT_E)
    dg.box("models", "runtime", 1150, 520, "Baked into the API image", [
        "FastEmbed all-MiniLM-L6-v2 cache and RapidOCR ONNX cache ship",
        "inside the image; HF_HUB_OFFLINE=1 keeps a cold start offline",
        "the AI health probe is cached, so /health stays fast",
    ], (240, 247, 240), RUNT_E, dy=330)
    dg.box("pg", "runtime", 2570, 300, "Supabase Postgres", [
        "DATABASE_URL (IPv4-pinned egress)",
        "users, matters, participants,",
        "documents, chunks + vectors,",
        "IngestionJob, rate_buckets,",
        "search_vector GIN index",
    ], EXT, EXT_E)
    dg.box("storage", "runtime", 2570, 300, "Supabase Storage", [
        "OBJECT_STORAGE=supabase (MinIO",
        "is QA-only); bucket from",
        "SUPABASE_STORAGE_BUCKET via",
        "the service-role key",
        "uploads, page bundles, exports",
        "05_DRAFTING_TEMPLATES ->",
        "drafting precedents (13 live)",
        "knowledge-base folder",
    ], EXT, EXT_E, dy=270)
    dg.box("claude", "runtime", 2570, 300, "Anthropic API", [
        "CLAUDE_MODEL = claude-haiku-5-5,",
        "AI_PROVIDER = anthropic",
        "a non-Claude model preference is ignored",
        "document summaries, grounded",
        "research answers, drafting",
        "output tagged ai_suggested /",
        "review_required; on failure the",
        "answer is model_unavailable,",
        "never a silent substitute",
    ], EXT, EXT_E, dy=540)
    dg.band("runtime", "3  RUNTIME — the path a stakeholder actually uses", RUNT, RUNT_E)

    # 4 ── proof ───────────────────────────────────────────────────────────────
    dg.box("smoke", "ops", 70, 640, "Proof after every deploy", [
        "scripts/prod_smoke.py: login -> matter -> participants -> upload ->",
        "/documents/{id}/ai-read -> grounded research -> /draft-templates ->",
        "draft -> corrupt-upload handling -> admin role 403 check",
        "scripts/prod_db.py prune-probes --prefix qa. (demo accounts are kept)",
    ], WHITE, OPS_E)
    dg.box("evidence", "ops", 860, 600, "Stakeholder evidence", [
        "frontend/scripts/stakeholder-evidence.mjs (Playwright: six reported",
        "defects + walkthrough cases T1-T6)",
        "scripts/build_evidence_report.py -> Markdown + PDF with claim",
        "verdicts and before/after screenshots; baseline in",
        "reports/evidence/before-prod is frozen",
    ], WHITE, OPS_E)
    dg.box("rollback", "ops", 1610, 600, "Rollback", [
        "same tooling, older tag:",
        "deploy_prod.py cloudrun --only backend|frontend --tag prod-<previous>",
        "then the hosting re-release",
        "Cloud Run keeps the revision history, nothing else changes",
    ], WHITE, OPS_E)
    dg.box("open", "ops", 2360, 510, "Open items for the next session", [
        "seed.remove_demo_data asserts consistency without re-checking the index",
        "drafts Generate lost its !template guard; the backend also accepts",
        "an empty document_type",
        "/draft-templates has no fallback when 05_DRAFTING_TEMPLATES is missing",
        "the improved system prompt is inert on the Anthropic path",
        "/calendar renders thin content; three Playwright specs never executed",
    ], NOTE, NOTE_E)
    dg.band("ops", "4  PROOF, ROLLBACK AND WHAT IS STILL OPEN", OPS, OPS_E, align="right")

    # arrows ───────────────────────────────────────────────────────────────────
    dg.arrow("git", "gates", "gates")
    dg.arrow("gates", "build", "green")
    dg.arrow("build", "deploy", "images")
    dg.arrow("creds", "deploy", "env names", dashed=True, color=NOTE_E, frm="l", to="r")
    dg.arrow("deploy", "ar", "push", dashed=True, color=(116, 96, 176), frm="b", to="t")
    dg.arrow("deploy", "runapi", "create / PATCH", color=(116, 96, 176), frm="b", to="t")
    dg.arrow("deploy", "hostapi", "hosting", dashed=True, color=(116, 96, 176), frm="b", to="t")
    dg.arrow("ar", "runapi", "image")
    dg.arrow("runapi", "hostapi", "release")
    dg.arrow("rules", "hostapi", "checks", dashed=True, color=NOTE_E, frm="l", to="r")

    dg.arrow("user", "edge", "HTTPS")
    dg.arrow("edge", "web", "/** pages")
    dg.arrow("web", "api", "rewrite (fallback)", dashed=True, color=RUNT_E)
    dg.arrow("models", "api", "cache", dashed=True, color=RUNT_E)
    dg.arrow("api", "pg", "SQL")
    dg.arrow("api", "storage", "objects")
    dg.arrow("api", "claude", "LLM")

    dg.arrow("api", "smoke", "live checks", dashed=True, color=OPS_E, frm="b", to="t", elbow=210)
    dg.arrow("smoke", "evidence")
    dg.arrow("evidence", "rollback")
    dg.arrow("rollback", "open")

    dg.render(
        "TANTRA — production deployment and runtime flow",
        "https://tantara-prod.web.app   ·   Firebase project tantra-513216   ·   Cloud Run region asia-south1   ·   "
        "live image tag prod-20261101-1446   ·   1 Nov 2026 (IST)",
        "reports/Tantra-Prod-Deployment-Flow.png",
    )


if __name__ == "__main__":
    main()
