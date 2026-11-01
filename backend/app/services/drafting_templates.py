"""Read approved drafting precedents from the shared Supabase Storage bucket."""

from __future__ import annotations

import io
from functools import lru_cache
from urllib.parse import quote

from app.config import get_settings
from app.supabase_storage import supabase_client

TEMPLATE_FOLDER = "05_DRAFTING_TEMPLATES"

# Template IDs are stable application IDs. The file paths stay server-side so
# clients cannot request arbitrary objects from the private storage bucket.
_TEMPLATES = (
    {
        "id": "precedent-01",
        "name": "TANTARA Precedent 01 · Notice Invoking Arbitration",
        "filename": "TANTARA Precedent 01 - Notice Invoking Arbitration.pdf",
        "document_type": "Notice Invoking Arbitration",
        "compatible_document_types": ["Notice Invoking Arbitration"],
    },
    {
        "id": "precedent-02",
        "name": "TANTARA Precedent 02 · Request for Arbitration and Response",
        "filename": "TANTARA Precedent 02 - Request for Arbitration and Response.pdf",
        "document_type": "Request for Arbitration",
        "compatible_document_types": ["Request for Arbitration", "Case Summary"],
    },
    {
        "id": "precedent-03",
        "name": "TANTARA Precedent 03 · Appointment of Arbitrator",
        "filename": "TANTARA Precedent 03 - Application for Appointment of Arbitrator and Opponent Response.pdf",
        "document_type": "Application for Appointment of Arbitrator",
        "compatible_document_types": ["Application for Appointment of Arbitrator"],
    },
    {
        "id": "precedent-04",
        "name": "TANTARA Precedent 04 · Statement of Claim and Defence",
        "filename": "TANTARA Precedent 04 - Statement of Claims and Defence.pdf",
        "document_type": "Statement of Claim",
        "compatible_document_types": ["Statement of Claim", "Statement of Defence"],
    },
    {
        "id": "precedent-05",
        "name": "TANTARA Precedent 05 · Reply to Counterclaim and Rejoinder",
        "filename": "TANTARA Precedent 05 - Reply to Counterclaim and Rejoinder.pdf",
        "document_type": "Rejoinder",
        "compatible_document_types": ["Rejoinder"],
    },
    {
        "id": "precedent-06",
        "name": "TANTARA Precedent 06 · Interim Relief Application",
        "filename": "TANTARA Precedent 06 - Interim Relief Application and Opposing Reply.pdf",
        "document_type": "Interim Relief Application",
        "compatible_document_types": ["Interim Relief Application"],
    },
    {
        "id": "precedent-07",
        "name": "TANTARA Precedent 07 · Jurisdictional Objection",
        "filename": "TANTARA Precedent 07 - Jurisdictional Objection and Response.pdf",
        "document_type": "Jurisdictional Objection",
        "compatible_document_types": ["Jurisdictional Objection"],
    },
    {
        "id": "precedent-08",
        "name": "TANTARA Precedent 08 · Procedural Applications",
        "filename": "TANTARA Precedent 08 - Procedural Applications and Response.pdf",
        "document_type": "Procedural Application",
        "compatible_document_types": ["Procedural Application"],
    },
    {
        "id": "precedent-09",
        "name": "TANTARA Precedent 09 · Witness Statements and Evidence Index",
        "filename": "TANTARA Precedent 09 - Witness Statements Evidence Index and Objections.pdf",
        "document_type": "Witness Statements and Evidence Index",
        "compatible_document_types": [
            "Witness Statements and Evidence Index",
            "Chronology of Events",
            "List of Dates",
        ],
    },
    {
        "id": "precedent-10",
        "name": "TANTARA Precedent 10 · Written Submissions",
        "filename": "TANTARA Precedent 10 - Written Submissions and Closing Arguments.pdf",
        "document_type": "Written Submissions",
        "compatible_document_types": ["Written Submissions", "Legal Research Memorandum"],
    },
    {
        "id": "precedent-11",
        "name": "TANTARA Precedent 11 · Set Aside or Challenge an Award",
        "filename": "TANTARA Precedent 11 - Set Aside or Challenge Award and Response.pdf",
        "document_type": "Set Aside or Challenge Award",
        "compatible_document_types": ["Set Aside or Challenge Award"],
    },
    {
        "id": "precedent-12",
        "name": "TANTARA Precedent 12 · Recognition and Enforcement of Awards",
        "filename": "TANTARA Precedent 12 - Recognition Enforcement Execution Awards.pdf",
        "document_type": "Recognition and Enforcement of Awards",
        "compatible_document_types": ["Recognition and Enforcement of Awards"],
    },
    {
        "id": "precedent-13",
        "name": "TANTARA Precedent 13 · Settlement Agreement and Consent Award",
        "filename": "TANTARA Precedent 13 - Settlement Agreement and Consent Award.pdf",
        "document_type": "Settlement Agreement and Consent Award",
        "compatible_document_types": ["Settlement Agreement and Consent Award"],
    },
)

_BY_ID = {template["id"]: template for template in _TEMPLATES}


class DraftingTemplateUnavailable(Exception):
    """The selected precedent could not be read from Supabase Storage."""


def list_drafting_templates() -> list[dict]:
    """Return safe metadata for the shared precedents, never their storage keys."""
    return [
        {
            "id": template["id"],
            "name": template["name"],
            "document_type": template["document_type"],
            "compatible_document_types": list(template["compatible_document_types"]),
            "source": "Supabase Storage",
        }
        for template in _TEMPLATES
    ]


def select_drafting_template(template_id: str | None, document_type: str) -> dict | None:
    if template_id:
        template = _BY_ID.get(template_id)
        if not template:
            raise ValueError("Unknown drafting template")
        return template
    document_type = document_type.casefold().strip()
    return next(
        (
            template
            for template in _TEMPLATES
            if any(value.casefold() == document_type for value in template["compatible_document_types"])
        ),
        None,
    )


@lru_cache(maxsize=13)
def load_drafting_template_text(template_id: str) -> str:
    template = _BY_ID.get(template_id)
    if not template:
        raise ValueError("Unknown drafting template")
    settings = get_settings()
    # Precedents always live in Supabase Storage, even when a local/test
    # workspace keeps case documents in an isolated filesystem store.
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise DraftingTemplateUnavailable("Supabase Storage is not configured")
    object_path = f"{TEMPLATE_FOLDER}/{template['filename']}"
    try:
        response = supabase_client().get(
            f"/storage/v1/object/{settings.supabase_storage_bucket}/{quote(object_path, safe='/')}"
        )
        response.raise_for_status()
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(response.content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001 - report a safe storage error to the caller
        raise DraftingTemplateUnavailable("Could not read the selected precedent") from exc
    if not text:
        raise DraftingTemplateUnavailable("The selected precedent contains no extractable text")
    return text
