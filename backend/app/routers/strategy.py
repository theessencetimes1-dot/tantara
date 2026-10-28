"""Auditable case strategy and explicit autofill preview/apply workflows."""

import json
import re
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import SessionLocal, session_scope
from app.models import AppPreference, Case, Document, ExtractionField, Hearing
from app.repositories.domain import get_owned
from app.security import current_user
from app.services.audit import record
from app.timezone import to_utc_iso

router = APIRouter(prefix="/api/v1/cases/{cid}", tags=["strategy", "autofill"])


class Keys(BaseModel):
    keys: list[str] = Field(default_factory=list)


class Fields(BaseModel):
    fields: list[dict] = Field(default_factory=list)


class StrategyBody(BaseModel):
    case_theory: str = ""
    key_issues: list[str] = Field(default_factory=list)
    legal_arguments: list[dict] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    strategy_plan: str = ""


def _case(s, cid, user):
    c = get_owned(s, Case, cid, user["id"])
    if not c:
        raise HTTPException(404, "Case not found")
    return c


@router.get("/autofill")
def autofill(cid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        c = _case(s, cid, user)
        keys = (
            "title",
            "reference_number",
            "claimant",
            "respondent",
            "forum",
            "seat",
            "governing_law",
            "dispute_category",
            "claim_amount",
            "claim_currency",
            "description",
            "filed_at",
            "notice_date",
            "limitation_date",
        )
        fields = [
            {
                "key": k,
                "label": k.replace("_", " ").title(),
                "value": getattr(c, k),
                "provenance": "verified",
                "source": "Case record",
            }
            for k in keys
            if getattr(c, k) is not None
        ]
        next_hearing = s.scalar(
            select(Hearing.at)
            .where(
                Hearing.owner_id == user["id"],
                Hearing.case_id == cid,
                Hearing.at >= datetime.now(UTC).replace(tzinfo=None),
            )
            .order_by(Hearing.at)
            .limit(1)
        )
        if next_hearing:
            fields.append(
                {
                    "key": "next_hearing_at",
                    "label": "Next Hearing",
                    "value": next_hearing,
                    "provenance": "verified",
                    "source": "Hearing record",
                }
            )
        docs = s.scalars(
            select(Document).where(Document.owner_id == user["id"], Document.case_id == cid)
        ).all()
        doc_ids = [d.id for d in docs]
        if doc_ids:
            rows = s.scalars(
                select(ExtractionField)
                .where(ExtractionField.owner_id == user["id"], ExtractionField.document_id.in_(doc_ids))
                .order_by(ExtractionField.created_at.desc())
            ).all()
            seen = {x["key"] for x in fields}
            for row in rows:
                if row.key not in seen:
                    doc = next((d for d in docs if d.id == row.document_id), None)
                    fields.append(
                        {
                            "key": row.key,
                            "label": row.key.replace("_", " ").title(),
                            "value": row.value,
                            "provenance": row.provenance,
                            "source": doc.title if doc else row.source,
                        }
                    )
                    seen.add(row.key)
        return {"status": "record_based", "model": None, "fields": fields}


@router.post("/autofill/preview")
def autofill_preview(cid: str, payload: Keys, user=Depends(current_user)):
    current = autofill(cid, user)
    wanted = set(payload.keys)
    return {"fields": [x for x in current["fields"] if x["key"] in wanted]}


@router.post("/autofill/apply")
def autofill_apply(cid: str, payload: Fields, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    allowed = {
        "claimant",
        "respondent",
        "forum",
        "seat",
        "governing_law",
        "arbitration_agreement_details",
        "dispute_category",
        "claim_amount",
        "claim_currency",
        "description",
        "filed_at",
        "notice_date",
        "limitation_date",
        "reference_number",
        "title",
    }
    applied = []
    skipped = []
    with session_scope() as s:
        c = _case(s, cid, user)
        for item in payload.fields:
            key = item.get("key")
            provenance = item.get("provenance")
            if key not in allowed or provenance not in {"verified", "extracted_reviewed", "ai_suggested"}:
                skipped.append(key)
                continue
            if getattr(c, key) is not None and provenance != "verified":
                skipped.append(key)
                continue
            if provenance == "ai_suggested":
                skipped.append(key)
                continue
            value = item.get("value")
            if key in {"filed_at", "notice_date", "limitation_date"} and value is not None:
                try:
                    value = date.fromisoformat(value) if isinstance(value, str) else value
                    if not isinstance(value, date):
                        raise ValueError("expected ISO date")
                except (TypeError, ValueError):
                    raise HTTPException(
                        422,
                        {
                            "message": "Request validation failed",
                            "details": [
                                {
                                    "loc": ["body", "fields", key, "value"],
                                    "msg": "Input should be a valid date in YYYY-MM-DD format",
                                    "type": "date_from_datetime_parsing",
                                }
                            ],
                        },
                    )
            setattr(c, key, value)
            applied.append(key)
        record(s, user["id"], "apply", "case_autofill", cid, {"applied": applied, "skipped": skipped})
    return {"applied": applied, "skipped": skipped}


def _get_strategy(s, cid, owner):
    row = s.scalar(
        select(AppPreference).where(AppPreference.owner_id == owner, AppPreference.key == f"strategy:{cid}")
    )
    return (
        row.value
        if row
        else {
            "case_theory": "",
            "key_issues": [],
            "legal_arguments": [],
            "counterarguments": [],
            "evidence_gaps": [],
            "strategy_plan": "",
            "updated_at": None,
            "status": "template",
            "model": None,
            "citations": [],
            "assertion_citations": [],
            "manually_edited": False,
            "generation_note": "No strategy has been generated for this case yet.",
        }
    )


@router.get("/strategy")
def strategy(cid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        _case(s, cid, user)
        return _get_strategy(s, cid, user["id"])


@router.post("/strategy/generate")
def generate_strategy(cid: str, user=Depends(current_user)):
    from app.config import get_settings
    from app.main import llm_answer
    from app.services.retrieval import retrieval_service

    with SessionLocal() as s:
        c = _case(s, cid, user)
        title = c.title
        docs = s.scalar(select(Document.id).where(Document.owner_id == user["id"], Document.case_id == cid))
    hits = (
        retrieval_service.search(f"issues evidence claims arbitration {title}", user["id"], 8, cid)
        if docs
        else []
    )
    citations = [
        {
            "document_id": hit["document_id"],
            "document_title": hit["document_title"],
            "chunk_id": hit["chunk_id"],
            "page_number": hit["page_number"],
            "snippet": hit["snippet"],
            "retrieval_score": hit.get("retrieval_score"),
        }
        for hit in hits
    ]
    now = to_utc_iso(datetime.now(UTC))
    model = None
    assertion_citations = []
    if not hits:
        result = {
            "case_theory": "",
            "key_issues": [],
            "legal_arguments": [],
            "counterarguments": [],
            "evidence_gaps": ["No indexed evidence was available for this case."],
            "strategy_plan": "",
            "updated_at": now,
            "generated_at": now,
            "status": "no_evidence",
            "model": None,
            "citations": [],
            "assertion_citations": [],
            "generation_note": "No indexed source evidence was available; no strategy was generated.",
            "manually_edited": False,
        }
    else:
        ai_settings = {}
        with SessionLocal() as s:
            pref = s.scalar(
                select(AppPreference).where(AppPreference.owner_id == user["id"], AppPreference.key == "ai")
            )
            ai_settings = pref.value if pref else {}
        settings = get_settings()
        model = ai_settings.get("model") or settings.local_llm_model
        prompt = (
            "Return JSON only with keys case_theory, key_issues, legal_arguments, counterarguments, "
            'evidence_gaps, strategy_plan. Each value is an object {"text":"...", "citations":["chunk-id"]}. '
            "Use only retrieved excerpts. Give one concise, evidence-bounded statement per section. "
            "Every non-empty text must cite one or more exact chunk IDs from the excerpts; citations cannot be empty. "
            "For counterarguments, give a question counsel should test, not an alleged fact. For evidence gaps, "
            "state what the excerpts do not establish and cite the reviewed excerpts. Make the plan a concrete "
            "verification step and cite its source. Do not invent facts, law, rules, or citations. CASE: "
            + title
        )
        raw = llm_answer(prompt, hits, base_url=ai_settings.get("base_url"), model=model, json_mode=True)
        parsed = None
        if raw:
            try:
                candidate = raw.strip()
                candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate)
                parsed = json.loads(candidate)
            except (ValueError, TypeError):
                parsed = None
        hit_by_chunk = {hit["chunk_id"]: citation for hit, citation in zip(hits, citations, strict=True)}
        validation_candidate = _validated_strategy(parsed, hit_by_chunk) if isinstance(parsed, dict) else None
        generated = validation_candidate if _has_strategy_minimum(validation_candidate) else None
        if generated:
            status = "model_generated"
            assertion_citations = generated.pop("assertion_citations")
            validation_warnings = generated.pop("validation_warnings")
            if not generated["legal_arguments"] and citations:
                first_source = citations[0]
                generated["legal_arguments"] = [
                    {
                        "statement": f"Source excerpt: {first_source['snippet']}",
                        "support": [first_source],
                    }
                ]
                assertion_citations.append(
                    {"field": "legal_arguments", "index": 0, "citations": [first_source]}
                )
                validation_warnings.append(
                    {"field": "legal_arguments", "index": None, "reason": "source_excerpt_fallback"}
                )
            generated["validation_warnings"] = validation_warnings
            generation_note = "Strategy generated by the configured local model from cited case evidence."
            if validation_warnings:
                generation_note = (
                    f"Strategy generated from cited case evidence; {len(validation_warnings)} unsupported "
                    "claim(s) were omitted. Review the validation warnings and source excerpts."
                )
            result = generated
        else:
            status = "model_unavailable" if raw is None else "template"
            generation_note = (
                "The configured model is unavailable; the content below is source excerpts assembled without a model."
                if status == "model_unavailable"
                else "The model did not return a valid, fully cited strategy; the content below is source excerpts assembled without a model."
            )
            result = {
                "case_theory": "",
                "key_issues": [],
                "legal_arguments": [
                    {
                        "statement": f"Source excerpt: {hit['snippet']}",
                        "support": [
                            {
                                "document_id": hit["document_id"],
                                "document_title": hit["document_title"],
                                "chunk_id": hit["chunk_id"],
                                "page_number": hit["page_number"],
                            }
                        ],
                    }
                    for hit in hits
                ],
                "counterarguments": [],
                "evidence_gaps": ["Retrieved excerpts do not address opposing evidence or governing law."],
                "strategy_plan": "",
                "validation_warnings": (
                    validation_candidate.get("validation_warnings", []) if validation_candidate else []
                ),
            }
            assertion_citations = [{"field": "evidence_gaps", "index": 0, "citations": citations}]
        result.update(
            {
                "updated_at": now,
                "generated_at": now,
                "status": status,
                "model": {"provider": "local", "model": model} if status == "model_generated" else None,
                "citations": citations,
                "assertion_citations": assertion_citations,
                "generation_note": generation_note,
                "manually_edited": False,
            }
        )
    with session_scope() as s:
        _case(s, cid, user)
        row = s.scalar(
            select(AppPreference).where(
                AppPreference.owner_id == user["id"], AppPreference.key == f"strategy:{cid}"
            )
        )
        if row:
            row.value = result
        else:
            s.add(
                AppPreference(id=str(uuid.uuid4()), owner_id=user["id"], key=f"strategy:{cid}", value=result)
            )
        record(s, user["id"], "generate", "case_strategy", cid)
    return {
        **result,
        "generation_kind": "model_strategy"
        if result["status"] == "model_generated"
        else "source_excerpt_review",
    }


def _validated_strategy(data, hit_by_chunk):
    """Keep independently valid claims and discard any claim with unresolved citations."""
    result = {"assertion_citations": [], "validation_warnings": []}

    def claim(value, field, index, output_index=None):
        if isinstance(value, dict):
            text = value.get("text", value.get("statement", ""))
            ids = value.get("citations", [])
            if not isinstance(text, str) or not isinstance(ids, list):
                result["validation_warnings"].append(
                    {"field": field, "index": index, "reason": "invalid_claim_shape"}
                )
                return None
            text = text.strip()
        else:
            result["validation_warnings"].append(
                {"field": field, "index": index, "reason": "invalid_claim_shape"}
            )
            return None
        sources = []
        for citation in ids:
            if not isinstance(citation, str):
                result["validation_warnings"].append(
                    {"field": field, "index": index, "reason": "citation_not_resolved"}
                )
                return None
            match = re.search(r"[0-9a-fA-F-]{36}", citation)
            chunk_id = match.group(0) if match else citation
            source = hit_by_chunk.get(chunk_id)
            cited_page = re.search(r"\bp\.(\d+)\b", citation)
            if not source or (cited_page and int(cited_page.group(1)) != source["page_number"]):
                result["validation_warnings"].append(
                    {"field": field, "index": index, "reason": "citation_not_resolved"}
                )
                return None
            sources.append(source)
        if not text or not sources:
            result["validation_warnings"].append(
                {"field": field, "index": index, "reason": "claim_has_no_cited_text"}
            )
            return None
        result["assertion_citations"].append(
            {"field": field, "index": index if output_index is None else output_index, "citations": sources}
        )
        return text

    theory = claim(data.get("case_theory", ""), "case_theory", 0) if data.get("case_theory") else ""
    result["case_theory"] = theory or ""
    for field in ("key_issues", "counterarguments", "evidence_gaps"):
        values = data.get(field, [])
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            result["validation_warnings"].append({"field": field, "index": None, "reason": "invalid_section_shape"})
            values = []
        texts = []
        for index, value in enumerate(values):
            text = claim(value, field, index, output_index=len(texts))
            if text is not None:
                texts.append(text)
        result[field] = texts
    args = data.get("legal_arguments", [])
    if isinstance(args, dict):
        args = [args]
    if not isinstance(args, list):
        result["validation_warnings"].append(
            {"field": "legal_arguments", "index": None, "reason": "invalid_section_shape"}
        )
        args = []
    result["legal_arguments"] = []
    for index, value in enumerate(args):
        output_index = len(result["legal_arguments"])
        text = claim(value, "legal_arguments", index, output_index=output_index)
        if text is not None:
            support = result["assertion_citations"][-1]["citations"]
            result["legal_arguments"].append({"statement": text, "support": support})
    plan = data.get("strategy_plan", [])
    if isinstance(plan, dict):
        plan = [plan]
    if not isinstance(plan, list):
        result["validation_warnings"].append(
            {"field": "strategy_plan", "index": None, "reason": "invalid_section_shape"}
        )
        plan = []
    plan_texts = []
    for index, value in enumerate(plan):
        text = claim(value, "strategy_plan", index, output_index=len(plan_texts))
        if text is not None:
            plan_texts.append(text)
    result["strategy_plan"] = "\n".join(plan_texts)
    return result


def _has_strategy_minimum(candidate):
    """A generated strategy needs a cited theory and at least one other supported section."""
    if not candidate or not candidate["case_theory"]:
        return False
    return any(
        (
            candidate["key_issues"],
            candidate["legal_arguments"],
            candidate["counterarguments"],
            candidate["evidence_gaps"],
            candidate["strategy_plan"],
        )
    )


@router.put("/strategy")
def strategy_put(cid: str, payload: StrategyBody, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        _case(s, cid, user)
        row = s.scalar(
            select(AppPreference).where(
                AppPreference.owner_id == user["id"], AppPreference.key == f"strategy:{cid}"
            )
        )
        result = {
            **payload.model_dump(),
            "updated_at": to_utc_iso(datetime.now(UTC)),
            "generated_at": row.value.get("generated_at") if row and isinstance(row.value, dict) else None,
            "status": row.value.get("status", "template")
            if row and isinstance(row.value, dict)
            else "template",
            "model": None,
            "citations": row.value.get("citations", []) if row and isinstance(row.value, dict) else [],
            "assertion_citations": [],
            "generation_note": "Manually edited by the case owner.",
            "manually_edited": True,
        }
        if row:
            row.value = result
        else:
            s.add(
                AppPreference(id=str(uuid.uuid4()), owner_id=user["id"], key=f"strategy:{cid}", value=result)
            )
        record(s, user["id"], "update", "case_strategy", cid)
    return result
