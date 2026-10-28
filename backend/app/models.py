"""Normalized SQLAlchemy 2.x domain schema. Vectors live in FAISS; BLOB is rebuild-only."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def now_utc():
    return datetime.now(UTC).replace(tzinfo=None)


def timestamps():
    return {
        "created_at": mapped_column(DateTime, default=now_utc, nullable=False),
        "updated_at": mapped_column(DateTime, default=now_utc, onupdate=now_utc, nullable=False),
    }


class Owned:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="advocate")
    avatar_initials: Mapped[str | None] = mapped_column(String(8))
    title: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
    __table_args__ = (
        CheckConstraint("role IN ('advocate','researcher','staff','admin')", name="ck_users_role"),
    )


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Client(Owned, Base):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(240))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active")
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive','archived')", name="ck_clients_status"),
    )


class Case(Owned, Base):
    __tablename__ = "cases"
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100))
    claimant: Mapped[str | None] = mapped_column(String(300))
    respondent: Mapped[str | None] = mapped_column(String(300))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    forum: Mapped[str | None] = mapped_column(String(100))
    seat: Mapped[str | None] = mapped_column(String(200))
    governing_law: Mapped[str | None] = mapped_column(String(200))
    arbitration_agreement_details: Mapped[str | None] = mapped_column(Text)
    dispute_category: Mapped[str | None] = mapped_column(String(100))
    claim_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    claim_currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notice_date: Mapped[datetime | None] = mapped_column(DateTime)
    limitation_date: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        CheckConstraint("status IN ('active','pending','closed','archived')", name="ck_cases_status"),
        Index("ix_cases_owner_status_updated", "owner_id", "status", "updated_at"),
        UniqueConstraint("owner_id", "reference_number", name="uq_cases_owner_reference"),
    )


class CaseParticipant(Owned, Base):
    __tablename__ = "case_participants"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    party_role: Mapped[str] = mapped_column(String(24), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(240))
    email: Mapped[str | None] = mapped_column(String(320))
    represented_by: Mapped[str | None] = mapped_column(String(240))
    __table_args__ = (
        CheckConstraint(
            "party_role IN ('claimant','respondent','arbitrator','counsel','witness')",
            name="ck_participant_role",
        ),
    )


class CaseEvent(Owned, Base):
    __tablename__ = "case_events"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")


class Hearing(Owned, Base):
    __tablename__ = "hearings"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="online")
    venue: Mapped[str | None] = mapped_column(String(300))
    forum: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("mode IN ('offline','online','virtual')", name="ck_hearing_mode"),)


class Task(Owned, Base):
    __tablename__ = "tasks"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    priority: Mapped[str] = mapped_column(String(12), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="todo")
    assignee: Mapped[str | None] = mapped_column(String(240))
    __table_args__ = (
        CheckConstraint("priority IN ('low','medium','high')", name="ck_task_priority"),
        CheckConstraint("status IN ('todo','in_progress','done')", name="ck_task_status"),
    )


class KnowledgeCollection(Owned, Base):
    __tablename__ = "knowledge_collections"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_collection_owner_name"),)


class Document(Owned, Base):
    __tablename__ = "documents"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), default="Other")
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    source_label: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    publisher: Mapped[str | None] = mapped_column(String(240))
    official_title: Mapped[str | None] = mapped_column(String(400))
    doc_date: Mapped[str | None] = mapped_column(String(40))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime)
    license_note: Mapped[str | None] = mapped_column(Text)
    citation_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    text_content: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    collection_id: Mapped[str | None] = mapped_column(String(36), index=True)
    __table_args__ = (
        UniqueConstraint("owner_id", "content_hash", name="uq_document_owner_hash"),
        Index("ix_documents_owner_case_status", "owner_id", "case_id", "status"),
    )


class DocumentPage(Owned, Base):
    __tablename__ = "document_pages"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_page"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)
    embedding_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index("ix_chunks_page", "document_id", "page_number"),
    )


class Draft(Owned, Base):
    __tablename__ = "drafts"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    content_markdown: Mapped[str] = mapped_column(Text, default="")
    template_id: Mapped[str | None] = mapped_column(String(80))


class DraftVersion(Owned, Base):
    __tablename__ = "draft_versions"
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (UniqueConstraint("draft_id", "version_number", name="uq_draft_version"),)


class Note(Owned, Base):
    __tablename__ = "notes"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="note")


class ResearchSession(Owned, Base):
    __tablename__ = "research_sessions"
    title: Mapped[str] = mapped_column(String(300), default="New research session")
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)


class ResearchMessage(Owned, Base):
    __tablename__ = "research_messages"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[dict] = mapped_column(JSON, default=dict)


class Citation(Owned, Base):
    __tablename__ = "citations"
    message_id: Mapped[str] = mapped_column(
        ForeignKey("research_messages.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text)
    retrieval_score: Mapped[float] = mapped_column(Float)


class FilingBundle(Owned, Base):
    __tablename__ = "filing_bundles"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"cover_page": True, "index": True, "synopsis": True, "list_of_dates": True}
    )
    status: Mapped[str] = mapped_column(String(24), default="draft")
    output_path: Mapped[str | None] = mapped_column(Text)


class BundleSection(Owned, Base):
    __tablename__ = "bundle_sections"
    bundle_id: Mapped[str] = mapped_column(ForeignKey("filing_bundles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)


class BundleItem(Owned, Base):
    __tablename__ = "bundle_items"
    bundle_id: Mapped[str] = mapped_column(ForeignKey("filing_bundles.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(240), default="Documents")
    order: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("bundle_id", "document_id", name="uq_bundle_document"),)


class CommunityPost(Owned, Base):
    __tablename__ = "community_posts"
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="discussion")
    visibility: Mapped[str] = mapped_column(
        String(16), default="private", server_default="private", nullable=False
    )
    case_ref: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (CheckConstraint("kind IN ('discussion','question')", name="ck_post_kind"),)


class CommunityReply(Owned, Base):
    __tablename__ = "community_replies"
    post_id: Mapped[str] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class CommunityTag(Base):
    __tablename__ = "community_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)


class SavedItem(Owned, Base):
    __tablename__ = "saved_items"
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("owner_id", "item_type", "item_id", name="uq_saved_item"),)


class AppPreference(Owned, Base):
    __tablename__ = "app_preferences"
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("owner_id", "key", name="uq_preference"),)


class IngestionJob(Owned, Base):
    __tablename__ = "ingestion_jobs"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    chars: Mapped[int] = mapped_column(Integer, default=0)


class AuditEvent(Owned, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ExtractionField(Owned, Base):
    __tablename__ = "extraction_fields"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str | None] = mapped_column(String(300))
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint(
            "provenance IN ('verified','extracted_reviewed','ai_suggested')", name="ck_extraction_provenance"
        ),
    )


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
