"""Pydantic v2 request/response contracts for typed API domains."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from app.timezone import workspace_now


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCreate(RequestModel):
    name: str = Field(min_length=1, max_length=240)
    organization: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: Literal["active", "inactive", "archived"] = "active"
    notes: str | None = None


class CaseCreate(RequestModel):
    title: str = Field(min_length=1, max_length=300)
    reference_number: str | None = None
    claimant: str | None = None
    respondent: str | None = None
    client_id: str | None = None
    forum: str | None = None
    seat: str | None = None
    governing_law: str | None = None
    arbitration_agreement_details: str | None = None
    dispute_category: str | None = None
    claim_amount: Decimal | None = None
    claim_currency: str | None = None
    status: Literal["active", "pending", "closed", "archived"] = "active"
    description: str | None = None
    filed_at: datetime | None = None
    next_hearing_at: datetime | None = None
    notice_date: datetime | None = None
    limitation_date: datetime | None = None

    @field_validator("filed_at")
    @classmethod
    def filed_date_must_not_be_in_future(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            now = workspace_now()
            filed_date = value.astimezone(now.tzinfo).date() if value.tzinfo else value.date()
            if filed_date > now.date():
                raise ValueError("Filing date cannot be in the future")
        return value


class HearingCreate(RequestModel):
    title: str = Field(min_length=1, max_length=300)
    at: datetime
    case_id: str | None = None
    mode: Literal["offline", "online", "virtual"] = "online"
    venue: str | None = None
    forum: str | None = None
    status: str = "scheduled"
    notes: str | None = None


class TaskCreate(RequestModel):
    title: str = Field(min_length=1, max_length=300)
    case_id: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["todo", "in_progress", "done"] = "todo"
    assignee: str | None = None


class DraftCreate(RequestModel):
    title: str = Field(min_length=1, max_length=300)
    case_id: str | None = None
    document_type: str
    status: str = "draft"
    content_markdown: str = ""
    template_id: str | None = None


class DraftPatch(RequestModel):
    title: str | None = None
    case_id: str | None = None
    document_type: str | None = None
    status: str | None = None
    content_markdown: str | None = None
    template_id: str | None = None

    @field_validator("content_markdown")
    @classmethod
    def content_must_not_be_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Draft content cannot be empty")
        return value


class BundleCreate(RequestModel):
    name: str = Field(min_length=1, max_length=300)
    case_id: str | None = None
    settings: dict = Field(
        default_factory=lambda: {"cover_page": True, "index": True, "synopsis": True, "list_of_dates": True}
    )
    status: str = "draft"


class NoteCreate(RequestModel):
    title: str = ""
    case_id: str | None = None
    body: str = ""
    kind: str = "note"


class CommunityPostCreate(RequestModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    kind: Literal["discussion", "question"] = "discussion"
    visibility: Literal["private", "workspace"] = "private"
    case_ref: str | None = None
    tags: list[str] = Field(default_factory=list)


CREATE_SCHEMAS = {
    "clients": ClientCreate,
    "cases": CaseCreate,
    "hearings": HearingCreate,
    "tasks": TaskCreate,
    "drafts": DraftCreate,
    "bundles": BundleCreate,
    "notes": NoteCreate,
    "community/posts": CommunityPostCreate,
}


def partial_schema(model, name):
    fields = {}
    for key, field in model.model_fields.items():
        typ = field.annotation
        if type(None) not in getattr(typ, "__args__", ()):
            typ = Optional[typ]
        fields[key] = (typ, None)
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


PATCH_SCHEMAS = {
    key: partial_schema(model, model.__name__.replace("Create", "Patch"))
    for key, model in CREATE_SCHEMAS.items()
}
PATCH_SCHEMAS["drafts"] = DraftPatch


class PageEnvelope(RequestModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    pages: int


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    document_title: str
    chunk_id: str
    page_number: int | None = None
    snippet: str
    retrieval_score: float
    source_type: str | None = None
    jurisdiction: str | None = None


class SearchResponse(BaseModel):
    status: str
    items: list[SearchHit]
    total: int
    page: int
    page_size: int
    pages: int


class ResearchCitation(BaseModel):
    model_config = ConfigDict(extra="allow")

    citation_ref: str
    citation_number: int
    document_id: str
    document_title: str
    chunk_id: str
    page_number: int | None = None
    excerpt: str
    retrieval_score: float
    source_type: str | None = None
    jurisdiction: str | None = None


class ResearchSupport(BaseModel):
    chunk_id: str
    document_id: str
    page_number: int | None = None
    quote: str


class ResearchMeta(BaseModel):
    retrieval_status: str


class ModelInfo(BaseModel):
    provider: str
    model: str


class AskResponse(BaseModel):
    status: str
    meta: ResearchMeta
    answer: str
    answer_kind: str
    citations: list[ResearchCitation]
    supports: list[ResearchSupport]
    answer_basis: str
    context_fields: list[dict[str, object]]
    conflicts: list[dict[str, object]]
    total: int
    citation_count: int
    follow_ups: list[str]
    model: ModelInfo | None
    disclaimer: str
    research_session_id: str | None
    message_id: str | None
