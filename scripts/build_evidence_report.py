#!/usr/bin/env python3
"""Build the stakeholder evidence report (Markdown + PDF) from an evidence run.

Reads two evidence runs — a before-fix run and an after-fix run — each produced by
frontend/scripts/stakeholder-evidence.mjs (results.json plus PNG screenshots), and
renders one Markdown file and one PDF for circulation.

Usage:
  backend/.venv/bin/python scripts/build_evidence_report.py \
      --before reports/evidence/before-prod --after reports/evidence/after-prod \
      --out-prefix reports/Tantra-Stakeholder-Evidence

Verdict language is deliberately plain: a stakeholder claim is reported as TRUE
(confirmed in the product), FALSE (not reproducible), PARTLY TRUE, or UNTESTED,
with the evidence that decided it next to the verdict.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
from xml.sax.saxutils import escape

from PIL import Image as PILImage  # PIL keeps the image sizing maths simple
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------- claim record
# id -> (group, stakeholder claim, what we found before the fixes, what was changed)
CLAIMS: dict[str, tuple[str, str, str, str]] = {
    "D1": (
        "Defect 1",
        "No clients can be selected in New Case — the name has to be typed.",
        "TRUE. The Client control offered only “Select client”: a new workspace has no clients and the form had no way to add one, so a matter could not be associated with a client at all.",
        "The New Case form now creates a client inline (type a name, press Enter, or use “＋ Add client”) and selects it; the picker announces the new client and the case list and detail pages show the client name.",
    ),
    "D2": (
        "Defect 2",
        "Two icons do not work: calendar and update (settings).",
        "NOT REPRODUCED on desktop: Calendar and Settings both navigate correctly, as do the bell, the account menu, global search and the task tick. The stakeholder was most likely on a narrow window where the sidebar collapses.",
        "Keyboard operation and focus handling were verified, the collapsed mobile sidebar was made scrollable, and a phone-width navigation check (390×844) was added to the evidence run so the claim can be confirmed either way.",
    ),
    "D3": (
        "Defect 3",
        "Upload is stuck on “Processing”.",
        "Reproduced in the code, not by the automated baseline. The uploaded row was hard-set to the word “Processing” with progress 100 and never updated from the job, so a finished document still looked stuck; the baseline scored CLAIM FALSE because the document record behind it did reach Ready in a second — it was the row, not the pipeline, that was stuck. On the stakeholder’s own account the upload could also fail outright: every visitor behind Firebase Hosting shared one 20-uploads-per-minute bucket, and the interface did not show the 429.",
        "The queue now polls the job and shows Uploading → Extracting → Indexing → Ready / Failed with a Retry button, and rate limiting is per signed-in user (60 uploads and 1200 reads per minute per user) instead of one shared bucket for every visitor. The after run then exposed a second, separate fault in the same panel: it crashed while rendering a freshly claimed job whose status had not been written yet (“a.toLowerCase is not a function”), which is exactly what made the row look broken; the render is now null-safe (with a regression test) and was re-checked in production — see D3b.",
    ),
    "D4": (
        "Defect 4",
        "Search is not fetching the document information.",
        "NOT reproduced: searching the reference TANTRA-TEST-2026-001 returned 8 passages with readable snippets, the first being page 1 of the uploaded agreement, with an “Open at page 1” jump. The condition that would produce the reported symptom is upstream of search — if the upload was refused (shared 20-per-minute quota) or had not finished indexing, there was simply nothing for search to fetch.",
        "No change was required for retrieval. Search behaviour is re-measured in the after run (hits, snippets, page jumps).",
    ),
    "D5": (
        "Defect 5",
        "AI extraction in the Documents section is not working.",
        "The panel did put text on screen, which is why the automated verdict reads CLAIM FALSE — but the AI half of it was genuinely dead: the panel itself said “Model unavailable — showing local text matches”, and /api/v1/ai/status named MiniCPM5-2B on a LAN address, because production was configured with a retired Claude model id (claude-sonnet-4-20250514) that Anthropic answers 404 for. Every AI feature in the product was affected.",
        "The model id was corrected to claude-haiku-5-5 with a valid key and redeployed; the extraction endpoint now calls the model and returns the model name, the source of every value and page-anchored quotes, and the panel shows the model that actually ran plus a clear notice when it is unreachable.",
    ),
    "T1a": ("Test 1", "A new matter can be created.", "TRUE — the matter was created and opened.", "No change required."),
    "T1b": (
        "Test 1",
        "Opening the matter shows parties, institution, amount and other details.",
        "PARTLY TRUE — the data was correct but the detail page rendered an empty card when the record arrived before the page finished mounting (a race).",
        "The create response is placed in the page cache before navigation and the header renders from the record with a skeleton while loading and a retryable error state.",
    ),
    "T1c": ("Test 1", "The matter appears in My Cases.", "TRUE — the matter appeared in the list.", "No change required."),
    "T1d": ("Test 1", "A task is created, linked to the matter and survives a refresh.", "TRUE.", "No change required."),
    "T1e": ("Test 1", "The calendar displays the task due date.", "TRUE — the 5 Nov 2026 deadline appeared on the calendar.", "No change required."),
    "T2a": ("Test 2", "An uploaded document reaches Ready.", "TRUE — Ready in 1 second for the one-page test file.", "No change required for the pipeline itself; recovery sweeps were added so an interrupted job is finished automatically instead of staying non-terminal."),
    "T2b": ("Test 2", "The extracted text of the uploaded document is readable.", "PARTLY TRUE — the text was stored and searchable but was hidden inside a collapsed “Extracted text by page” disclosure.", "A first-page preview is now shown without expanding anything."),
    "T2c": (
        "Test 2",
        "The research desk answers all five questions about the uploaded agreement.",
        "FALSE — the desk answered parties correctly but not the reference, the seat or the sole-arbitrator question, because no language model was reachable; answers fell back to quoted excerpts.",
        "The model was made reachable (claude-haiku-5-5) and the uploaded agreement is indexed, so the desk can answer from the document.",
    ),
    "T3a": (
        "Test 3",
        "The research desk explains Sections 9 and 17 with citations.",
        "PARTLY TRUE — the corpus passages and 16 citation chips were correct, but no model synthesis was possible (“model generated answer: false”).",
        "Model synthesis is enabled again; the answer is now produced by claude-haiku-5-5 over the retrieved passages.",
    ),
    "T3b": ("Test 3", "Citation chips link to the cited document page.", "TRUE — 16 citation chips opened the right page.", "No change required."),
    "T4": (
        "Test 4",
        "The draft builder produces a usable draft with marked missing facts and no invented facts.",
        "FALSE — it produced a template skeleton with [REVIEW: …] filler, no citations and no reference to the ₹12,50,000 invoice in the record, because the model was unreachable.",
        "The drafting prompt now forbids invented invoice numbers, dates, addresses, prior notices, payments and case law, demands a demand section and a response deadline, and marks every missing fact with [TO BE CONFIRMED]; when the model is unavailable the service returns an explicit “model unavailable” status and message instead of a hollow draft.",
    ),
    "T5": (
        "Test 5",
        "The bundle merges selected documents into a downloadable PDF.",
        "UNTESTED IN THE FIRST PASS — the evidence script sent the wrong field name, which is our test bug, not the product’s; the bundle endpoint answered 422.",
        "The evidence script was corrected (name, not title) and the bundle path — create, add documents, generate, download a real PDF — is re-measured in the after run.",
    ),
    "T6a": ("Test 6", "One advocate cannot see another advocate’s matters.", "TRUE — no case rows, no case-search hits, no cross-account document search.", "No change required."),
    "T6b": (
        "Test 6",
        "A read-only researcher is refused uploads with 403 “This role is read-only”.",
        "UNTESTED — self-signup always creates an advocate, so the read-only role could not be reached from the public UI.",
        "Read-only roles were seeded directly in production (demo.researcher@theessencetimes.com), and the after run signs in as that account to show the 403 and to confirm the researcher can still read the shared library.",
    ),
    "AI1": (
        "AI health",
        "The product reports the AI provider, model and reachability it actually uses.",
        "FALSE — /api/v1/ai/status answered provider=anthropic but model=MiniCPM5-2B and a private LAN base_url, which is how the broken configuration stayed invisible.",
        "The status endpoint now probes the real provider, names the model that will actually be used, and no longer leaks a LAN address for cloud providers.",
    ),
    "T2d": (
        "Test 2",
        "A real multi-page statute PDF uploads, indexes and leaves the queue without a page reload.",
        "NOT MEASURED IN THE FIRST PASS (a one-page text file was used).",
        "The after run uploads Specific Relief Act, 1963.pdf (17 pages) and watches the queue to Ready with no reload.",
    ),
}

VERDICT_STYLE = {
    "pass": "PASS",
    "fail": "FAIL",
    "confirmed": "CLAIM TRUE",
    "not confirmed": "CLAIM FALSE",
    "partial": "PARTLY TRUE",
    "blocked": "UNTESTED",
    "testable": "UNTESTED",
}


def load_run(directory: pathlib.Path) -> dict:
    results = json.loads((directory / "results.json").read_text())
    for item in results["results"]:
        shot = item.get("shot")
        if not shot:
            continue
        candidate = pathlib.Path(shot)
        if not candidate.is_absolute():
            candidate = directory / candidate
        if not candidate.exists():
            sibling = directory / pathlib.Path(shot).name
            if sibling.exists():
                candidate = sibling
        item["shot"] = str(candidate)
    return {item["id"]: item for item in results["results"]}, results


def verdict_label(verdict: str, is_defect: bool) -> str:
    if is_defect:
        return VERDICT_STYLE.get(verdict, verdict.upper())
    return VERDICT_STYLE.get(verdict, verdict.upper())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", default="reports/evidence/before-prod")
    parser.add_argument("--after", default="reports/evidence/after-prod")
    parser.add_argument("--out-prefix", default="reports/Tantra-Stakeholder-Evidence")
    args = parser.parse_args()

    before_dir = pathlib.Path(args.before).resolve()
    after_dir = pathlib.Path(args.after).resolve()
    before, before_meta = load_run(before_dir)
    after, after_meta = load_run(after_dir)

    out_md = pathlib.Path(f"{args.out_prefix}.md")
    out_pdf = pathlib.Path(f"{args.out_prefix}.pdf")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    def run_ids(cid: str, runs: dict) -> list[str]:
        """D2 was measured per icon and per device, so aggregate those sub-checks."""
        if cid == "D2":
            return sorted(k for k in runs if k == "D2" or k.startswith("D2-") or k.startswith("D2m-"))
        return [cid] if cid in runs else []

    def sub_label(sub: str, cid: str, runs: dict) -> str:
        if sub == cid:
            return ""
        claim = str(runs.get(sub, {}).get("claim", "")) or sub
        claim = claim.replace("Claim: ", "").strip()
        return f" — {claim[:58]}" if claim else f" ({sub})"

    def aggregate(cid: str, runs: dict) -> str:
        ids = run_ids(cid, runs)
        verdicts = [runs[k]["verdict"] for k in ids]
        if not verdicts:
            return "blocked"
        if len(verdicts) == 1:
            return verdicts[0]
        if any(v in ("confirmed", "fail") for v in verdicts):
            return "confirmed" if cid.startswith("D") else "fail"
        if all(v in ("not confirmed", "pass") for v in verdicts):
            return "not confirmed" if cid.startswith("D") else "pass"
        return "partial"

    def stakeholder_right(cid: str, verdict: str) -> str:
        is_defect = cid.startswith("D")
        if verdict == "blocked":
            return "Not established"
        if verdict == "partial":
            return "Partly"
        if is_defect:
            return "Yes" if verdict in ("confirmed", "fail") else "No"
        return "Yes" if verdict == "fail" else "No"

    order = [cid for cid in CLAIMS if run_ids(cid, before) or run_ids(cid, after)]
    groups: dict[str, list[str]] = {}
    for cid in order:
        group = CLAIMS[cid][0]
        groups.setdefault(group, []).append(cid)

    # ------------------------------------------------------------ markdown
    lines: list[str] = []
    lines.append("# TanTRA — stakeholder evidence report")
    lines.append("")
    lines.append(
        f"Site tested: **{before_meta['site']}** · before run {before_meta['ranAt'][:16].replace('T', ' ')} IST · "
        f"after run {after_meta['ranAt'][:16].replace('T', ' ')} IST · all checks driven through the real user interface in a real browser."
    )
    lines.append("")
    corrections = after_meta.get("corrections") or []
    if corrections:
        lines.append("### Corrections made to the measuring script after the run")
        lines.append("")
        for note in corrections:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Headline")
    lines.append("")
    lines.append(
        "| Reported problem | Was the stakeholder right? | Position after the fixes |"
    )
    lines.append("|---|---|---|")
    for cid in ["D1", "D2", "D3", "D4", "D5", "T2c", "T3a", "T4", "T5"]:
        group, claim, was, fixed = CLAIMS[cid]
        b = aggregate(cid, before)
        a = aggregate(cid, after)
        right = stakeholder_right(cid, b)
        lines.append(
            f"| {cid} — {claim} | {right} (measured before: {verdict_label(b, cid.startswith('D'))}) "
            f"| after the fixes: {verdict_label(a, cid.startswith('D'))} |"
        )
    lines.append("")
    lines.append(
        "Two configuration faults and three deployment faults explain almost everything. **(1)** The AI was configured with a Claude "
        "model id that Anthropic no longer recognises (404), so every model call failed and the product fell back to quoting excerpts. "
        "**(2)** The rate limiter counted every visitor of the site as one client, so the whole workspace shared 20 uploads a minute. "
        "**(3)** The deployment script pushed a stale local image under every new tag, so three \"successful\" deploys changed nothing. "
        "**(4)** The Cloud Run revision never declared the container port, so two revisions failed their health check and the service "
        "silently kept serving the previous version. **(5)** Firebase Hosting served year-cached HTML for released pages, so browsers "
        "kept the old interface after the new build was live. The remaining defects were interface-level: a client picker with no way to "
        "add a client, an upload queue that never updated, a matter page that could render empty, and text hidden behind a collapsed "
        "disclosure."
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        "Each journey is replayed by a scripted browser (`frontend/scripts/stakeholder-evidence.mjs`) against the live site with a "
        "freshly registered account, and every claim is decided from what the interface actually showed plus what the API returned. "
        "Screenshots in this report are those captures. An earlier \"after\" run at 15:38 IST was discarded and is kept in "
        "`reports/evidence/mid-prod/` for the audit trail: at that moment the fixes had not actually reached production, which is how "
        "deployment faults (3)–(5) were found."
    )
    lines.append("")

    for cid in order:
        group, claim, was, fixed = CLAIMS[cid]
        b = before.get(cid)
        a = after.get(cid)
        is_defect = cid.startswith("D")
        lines.append(f"## {cid} — {claim}")
        lines.append("")
        lines.append(f"*{group}*")
        lines.append("")
        lines.append("| | Verdict | What the run recorded |")
        lines.append("|---|---|---|")
        sub_ids = run_ids(cid, before) or run_ids(cid, after)
        for sub in sub_ids if len(sub_ids) > 1 else [cid]:
            suffix = sub_label(sub, cid, before) or sub_label(sub, cid, after)
            for label, run in (("Before the fixes", before.get(sub)), ("After the fixes", after.get(sub))):
                if run is None:
                    lines.append(f"| {label}{suffix} | not measured | — |")
                else:
                    detail = str(run.get("detail", "")).replace("|", "/").replace("\n", " ")
                    lines.append(f"| {label}{suffix} | {verdict_label(run['verdict'], is_defect)} | {detail} |")
        lines.append("")
        lines.append(f"**What we found:** {was}")
        lines.append("")
        lines.append(f"**What was changed:** {fixed}")
        lines.append("")
        shots = []
        sub_ids = run_ids(cid, before) or run_ids(cid, after) or [cid]
        for label, side in (("before", before), ("after", after)):
            for sub in sub_ids:
                run = side.get(sub)
                if not run or not run.get("shot"):
                    continue
                src = pathlib.Path(run["shot"])
                if not src.exists():
                    continue
                dest_dir = out_md.parent / "evidence" / f"{label}-{src.parent.name}"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                suffix = "" if sub == cid else f" ({sub.split('-', 1)[-1]})"
                shots.append(f"![{cid}{suffix} {label}](evidence/{label}-{src.parent.name}/{src.name})")
        if shots:
            lines.extend(shots)
            lines.append("")

    extra = sorted((set(before) | set(after)) - set(CLAIMS))
    if extra:
        lines.append("## Other checks measured along the way")
        lines.append("")
        lines.append("These are not stakeholder claims; they are the checks that prove nothing else broke.")
        lines.append("")
        lines.append("| Check | Before | After | What the run recorded |")
        lines.append("|---|---|---|---|")
        for cid in extra:
            is_defect = cid.startswith("D")
            b = before.get(cid)
            a = after.get(cid)
            detail = str((a or b or {}).get("detail", "")).replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {cid} | {verdict_label(b['verdict'], is_defect) if b else 'not measured'} "
                f"| {verdict_label(a['verdict'], is_defect) if a else 'not measured'} | {detail[:220]} |"
            )
        lines.append("")

    md_text = "\n".join(lines) + "\n"
    out_md.write_text(md_text)

    # ------------------------------------------------------------------ pdf
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1x", parent=styles["Title"], fontSize=20, spaceAfter=6)
    h2 = ParagraphStyle("h2x", parent=styles["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("bodyx", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("smallx", parent=styles["BodyText"], fontSize=7.5, leading=9.5, textColor=colors.HexColor("#444444"))
    cell = ParagraphStyle("cellx", parent=body, fontSize=8, leading=10)

    story = []
    story.append(Paragraph("TanTRA — stakeholder evidence report", h1))
    story.append(
        Paragraph(
            f"Site tested: {before_meta['site']} · before run {before_meta['ranAt'][:16].replace('T', ' ')} IST · "
            f"after run {after_meta['ranAt'][:16].replace('T', ' ')} IST · every check driven through the real interface in a real browser.",
            body,
        )
    )
    story.append(Spacer(1, 6))

    summary_rows = [["ID", "Reported problem", "Stakeholder right?", "After fixes"]]
    for cid in ["D1", "D2", "D3", "D4", "D5", "T2c", "T3a", "T4", "T5"]:
        b = aggregate(cid, before)
        a = aggregate(cid, after)
        summary_rows.append(
            [
                cid,
                Paragraph(escape(CLAIMS[cid][1]), cell),
                stakeholder_right(cid, b),
                verdict_label(a, cid.startswith("D")),
            ]
        )
    table = Table(summary_rows, colWidths=[14 * mm, 82 * mm, 30 * mm, 34 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c9c9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Five faults explain what was reported. The configured Claude model id is no longer recognised by Anthropic, so every AI call failed. "
            "The rate limiter keyed on client IP only, so every visitor of the deployed site shared one 20-requests-a-minute budget. The deployment "
            "script re-tagged a stale local image, so three \"successful\" deploys changed nothing. The Cloud Run update omitted the container port, "
            "so new revisions failed their health check and the service kept serving the previous revision. Released HTML was cached for a year, so "
            "browsers kept the old interface after the new build went live. The remaining defects were interface-level: a client picker with no way to "
            "add or select a client, an upload queue that never updated, a matter page that could render empty, and extracted text hidden behind a "
            "collapsed disclosure.",
            body,
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("How this was measured", h1))
    story.append(
        Paragraph(
            "Each journey is replayed by a scripted browser against the live site with a freshly registered account, and every claim is decided from "
            "what the interface actually showed plus what the API returned; the screenshots here are those captures. An earlier \"after\" run was "
            "discarded and kept in reports/evidence/mid-prod/ for the audit trail: at that moment the fixes had not actually reached production, "
            "which is how the deployment faults were found.",
            body,
        )
    )
    if corrections:
        story.append(Paragraph("Corrections made to the measuring script after the run", h1))
        for note in corrections:
            story.append(Paragraph(f"\u2022 {escape(note)}", body))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    for cid in order:
        group, claim, was, fixed = CLAIMS[cid]
        b = before.get(cid)
        a = after.get(cid)
        is_defect = cid.startswith("D")
        story.append(Paragraph(f"{cid} — {claim}", h2))
        story.append(Paragraph(group, small))
        sub_ids = run_ids(cid, before) or run_ids(cid, after) or [cid]
        rows = [["Run", "Verdict", "Recorded evidence"]]
        for sub in sub_ids:
            suffix = sub_label(sub, cid, before) or sub_label(sub, cid, after)
            for label, side in (("Before the fixes", before), ("After the fixes", after)):
                run = side.get(sub)
                if run is None:
                    rows.append([label + suffix, "not measured", Paragraph("—", cell)])
                else:
                    detail = escape(str(run.get("detail", ""))[:420])
                    rows.append([label + suffix, verdict_label(run["verdict"], is_defect), Paragraph(detail, cell)])
        t = Table(rows, colWidths=[30 * mm, 26 * mm, 104 * mm], repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c9c9")),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>What we found:</b> {was}", body))
        story.append(Paragraph(f"<b>What was changed:</b> {fixed}", body))
        for label, side in (("Before", before), ("After", after)):
            for sub in sub_ids:
                run = side.get(sub)
                if not run or not run.get("shot"):
                    continue
                src = pathlib.Path(run["shot"])
                if not src.exists():
                    continue
                suffix = "" if sub == cid else f" ({sub})"
                story.append(Paragraph(f"{label}{suffix} — {src.name}", small))
                with PILImage.open(src) as handle:
                    width, height = handle.size
                target_width = 160 * mm
                target_height = target_width * height / width
                if target_height > 92 * mm:
                    target_height = 92 * mm
                    target_width = target_height * width / height
                story.append(Image(str(src), width=target_width, height=target_height))
                story.append(Spacer(1, 6))
        story.append(PageBreak())

    doc = None
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = __import__("reportlab.platypus", fromlist=["SimpleDocTemplate"]).SimpleDocTemplate(
        str(out_pdf), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title="TanTRA stakeholder evidence report",
    )
    if extra:
        story.append(Paragraph("Other checks measured along the way", h1))
        extra_rows = [["Check", "Before", "After", "Recorded"]]
        for cid in extra:
            is_defect = cid.startswith("D")
            b = before.get(cid)
            a = after.get(cid)
            detail = escape(str((a or b or {}).get("detail", "")))[:200]
            extra_rows.append(
                [
                    cid,
                    verdict_label(b["verdict"], is_defect) if b else "not measured",
                    verdict_label(a["verdict"], is_defect) if a else "not measured",
                    Paragraph(detail, cell),
                ]
            )
        extra_table = Table(extra_rows, colWidths=[26 * mm, 24 * mm, 24 * mm, 86 * mm], repeatRows=1)
        extra_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c9c9")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fb")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(extra_table)

    doc.build(story)
    print(f"wrote {out_md} ({out_md.stat().st_size:,} bytes)")
    print(f"wrote {out_pdf} ({out_pdf.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
