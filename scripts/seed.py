#!/usr/bin/env python3
"""Create a typed demo workspace with real locally generated and indexed PDFs."""

import argparse
import io
import shutil
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings
from app.db import init_db, session_scope
from app.models import (
    AIConversation,
    AppPreference,
    AuditEvent,
    BundleItem,
    BundleSection,
    Case,
    CaseEvent,
    CaseParticipant,
    Citation,
    Client,
    CommunityPost,
    CommunityReply,
    CommunityTag,
    Document,
    DocumentChunk,
    DocumentPage,
    Draft,
    DraftVersion,
    ExtractionField,
    FilingBundle,
    KnowledgeCollection,
    Hearing,
    IngestionJob,
    Note,
    ResearchMessage,
    ResearchSession,
    SavedItem,
    Session,
    Task,
    User,
)
from app.routers.documents import process_job
from app.security import hash_password
from sqlalchemy import delete, func, select, text


def make_pdf(path, title, paragraphs, blank_last=False):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(title)
    for page_number in range(1, 6):
        if blank_last and page_number == 5:
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, 1, 1, fill=1, stroke=0)
            c.showPage()
            continue
        y = 740
        c.setFont("Helvetica-Bold", 15)
        c.drawString(52, y, f"{title} — Page {page_number}")
        y -= 35
        c.setFont("Helvetica", 11)
        paragraph = paragraphs[(page_number - 1) % len(paragraphs)]
        words = paragraph.split()
        line = ""
        for word in words:
            trial = (line + " " + word).strip()
            if len(trial) > 92:
                c.drawString(52, y, line)
                y -= 17
                line = word
            else:
                line = trial
        if line:
            c.drawString(52, y, line)
            y -= 22
        c.showPage()
    c.save()


def make_scanned_pdf(path):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=35)
    y = 150
    lines = [
        "ARBITRATION AGREEMENT",
        "",
        "The parties agree that disputes shall be referred",
        "to arbitration under the Arbitration and",
        "Conciliation Act, 1996. The seat shall be Mumbai.",
        "A single neutral will hear the dispute.",
    ]
    for line in lines:
        draw.text((115, y), line, fill="black", font=font)
        y += 100
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(5):
        c.drawImage(ImageReader(buf), 0, 0, width=612, height=792)
        c.showPage()
    c.save()


DEMO_COLLECTIONS = (
    ("Agreements & Contracts", "Agreements, contract terms, and arbitration clauses."),
    ("Awards & Authorities", "Awards, authorities, and procedural decisions."),
    ("Pleadings & Evidence", "Pleadings, motions, and supporting evidence."),
)


def ensure_demo_collections(db, owner_id):
    collections = {}
    for name, description in DEMO_COLLECTIONS:
        collection = db.scalar(
            select(KnowledgeCollection).where(
                KnowledgeCollection.owner_id == owner_id, KnowledgeCollection.name == name
            )
        )
        if collection is None:
            collection = KnowledgeCollection(
                id=str(uuid.uuid4()), owner_id=owner_id, name=name, description=description, is_demo=True
            )
            db.add(collection)
            db.flush()
        collections[name] = collection.id
    return collections


def seed_junior_workspace():
    """Create a researcher-owned demo matter for real cross-account checks."""
    settings = get_settings()
    with session_scope() as db:
        junior = db.scalar(select(User).where(User.email == "researcher@tantara.local"))
        if junior is None:
            junior = User(
                id=str(uuid.uuid4()),
                name="Mira Shah",
                email="researcher@tantara.local",
                password_hash=hash_password(settings.tantara_admin_password),
                role="researcher",
                avatar_initials="MS",
                title="Researcher",
            )
            db.add(junior)
            db.flush()
        owner = junior.id
        collections = ensure_demo_collections(db, owner)
        for document in db.scalars(
            select(Document).where(Document.owner_id == owner, Document.is_demo.is_(True))
        ):
            document.collection_id = collections["Pleadings & Evidence"]
        if db.scalar(select(Client.id).where(Client.owner_id == owner, Client.is_demo.is_(True))):
            return
        client = Client(
            id=str(uuid.uuid4()),
            owner_id=owner,
            name="Junior Demo Client",
            organization="Junior Demo",
            email="junior-client@example.local",
            status="active",
            notes="Isolated demo client",
            is_demo=True,
        )
        db.add(client)
        db.flush()
        case = Case(
            id=str(uuid.uuid4()),
            owner_id=owner,
            client_id=client.id,
            title="Junior Demo Matter",
            reference_number="ARB/JR/001",
            claimant="Junior Client",
            respondent="Sample Respondent",
            forum="SIAC",
            seat="Singapore",
            status="active",
            description="Researcher-owned demo case",
            is_demo=True,
        )
        bundle = FilingBundle(
            id=str(uuid.uuid4()),
            owner_id=owner,
            case_id=case.id,
            name="Junior Demo Bundle",
            settings={},
            status="draft",
            is_demo=True,
        )
        draft = Draft(
            id=str(uuid.uuid4()),
            owner_id=owner,
            case_id=case.id,
            title="Junior Research Note",
            document_type="Research Note",
            status="draft",
            content_markdown="# Junior research note\n",
            is_demo=True,
        )
        post = CommunityPost(
            id=str(uuid.uuid4()),
            owner_id=owner,
            title="Junior demo discussion",
            body="A researcher-owned sample discussion.",
            kind="discussion",
            visibility="workspace",
            tags=["commercial"],
            case_ref=case.id,
            is_demo=True,
        )
        db.add_all(
            [
                case,
                bundle,
                draft,
                post,
                Task(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=case.id,
                    title="Junior demo research task",
                    due_at=datetime.combine(date.today() + timedelta(days=5), datetime.min.time()),
                    status="todo",
                    priority="medium",
                    is_demo=True,
                ),
                Hearing(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=case.id,
                    title="Junior demo hearing",
                    at=datetime.combine(date.today() + timedelta(days=10), datetime.min.time()).replace(
                        hour=10
                    ),
                    status="scheduled",
                    mode="online",
                    is_demo=True,
                ),
            ]
        )

        fixture = settings.data_dir / "demo-fixtures" / "junior-demo.pdf"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        make_pdf(
            fixture,
            "Junior Demo Evidence",
            ["JuniorEvidenceMarker proves this document belongs to the researcher demo workspace."],
        )
        blob = fixture.read_bytes()
        document_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        stored = __import__("app.ingestion", fromlist=["DocumentStorage"]).DocumentStorage().save(blob)
        doc = Document(
            id=document_id,
            owner_id=owner,
            case_id=case.id,
            collection_id=collections["Pleadings & Evidence"],
            title="Junior Demo Evidence",
            document_type="Research Note",
            jurisdiction="India",
            filename="junior-demo.pdf",
            stored_path=stored,
            content_hash=__import__("hashlib").sha256(blob).hexdigest(),
            status="queued",
            is_demo=True,
        )
        db.add(doc)
        db.flush()
        db.add_all(
            [
                IngestionJob(
                    id=job_id,
                    owner_id=owner,
                    document_id=document_id,
                    status="queued",
                    steps=[],
                    warnings=[],
                    is_demo=True,
                ),
                BundleItem(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    bundle_id=bundle.id,
                    document_id=document_id,
                    section="Junior Evidence",
                    order=0,
                    is_demo=True,
                ),
            ]
        )
    process_job(document_id, job_id, owner, blob, "junior-demo.pdf")
    with session_scope() as db:
        db.add(
            CommunityReply(
                id=str(uuid.uuid4()),
                owner_id=owner,
                post_id=post.id,
                body="Junior workspace reply.",
                is_demo=True,
            )
        )


def seed_community_workspace():
    """Create stable cross-author workspace posts and replies for demo accounts."""
    settings = get_settings()
    with session_scope() as db:
        root = db.scalar(select(User).where(User.email == "advocate@tantara.local"))
        authors = []
        for email, name, role, initials in (
            ("researcher@tantara.local", "Mira Shah", "researcher", "MS"),
            ("staff@tantara.local", "Dev Patel", "staff", "DP"),
        ):
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=str(uuid.uuid4()),
                    name=name,
                    email=email,
                    password_hash=hash_password(settings.tantara_admin_password),
                    role=role,
                    avatar_initials=initials,
                    title=role.title(),
                )
                db.add(user)
                db.flush()
            authors.append(user)
        if root is None:
            return
        # Keep one explicit advocate-authored workspace thread so the
        # researcher feed demonstrates all three seeded identities.
        root_post = db.scalar(
            select(CommunityPost).where(
                CommunityPost.owner_id == root.id,
                CommunityPost.title == "Demo: case practice discussion 1",
            )
        )
        if root_post is not None:
            root_post.visibility = "workspace"
        posts = []
        for author in authors:
            for index in range(1, 3):
                title = f"Workspace demo: {author.name} discussion {index}"
                post = db.scalar(
                    select(CommunityPost).where(
                        CommunityPost.owner_id == author.id,
                        CommunityPost.title == title,
                    )
                )
                if post is None:
                    post = CommunityPost(
                        id=str(uuid.uuid4()),
                        owner_id=author.id,
                        title=title,
                        body="Demo workspace discussion. Replies are shared with workspace readers.",
                        kind="discussion" if index == 1 else "question",
                        visibility="workspace",
                        tags=["commercial", "procedure"],
                        is_demo=True,
                    )
                    db.add(post)
                    db.flush()
                else:
                    post.visibility = "workspace"
                posts.append(post)
        posts = db.scalars(
            select(CommunityPost).where(
                CommunityPost.owner_id.in_([author.id for author in authors]),
                CommunityPost.visibility == "workspace",
            )
        ).all()
        for post in posts:
            respondent = next(author for author in authors if author.id != post.owner_id)
            for author, body in (
                (root, "Advocate demo reply: review the source documents before relying on a position."),
                (respondent, "Colleague demo reply: identify any contrary material in the record."),
            ):
                if not db.scalar(
                    select(CommunityReply.id).where(
                        CommunityReply.post_id == post.id,
                        CommunityReply.owner_id == author.id,
                        CommunityReply.body == body,
                    )
                ):
                    db.add(
                        CommunityReply(
                            id=str(uuid.uuid4()),
                            owner_id=author.id,
                            post_id=post.id,
                            body=body,
                            is_demo=True,
                        )
                    )
        db.flush()


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--empty", action="store_true")
    args = parser.parse_args()
    init_db()
    s = get_settings()
    with session_scope() as db:
        root = db.scalar(select(User).where(User.email == "advocate@tantara.local"))
        if root is None:
            root = User(
                id=str(uuid.uuid4()),
                name="Workspace Advocate",
                email="advocate@tantara.local",
                password_hash=hash_password(s.tantara_admin_password),
                role="advocate",
                avatar_initials="AM",
                title="Advocate",
            )
            db.add(root)
            db.flush()
        owner = root.id
        if args.empty:
            paths = [
                x[0] for x in db.execute(select(Document.stored_path).where(Document.owner_id == owner)).all()
            ]
            document_ids = db.scalars(select(Document.id).where(Document.owner_id == owner)).all()
            if document_ids:
                db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)))
            for model in (
                AuditEvent,
                AppPreference,
                SavedItem,
                AIConversation,
                ExtractionField,
                CaseEvent,
                CaseParticipant,
                DocumentPage,
                DraftVersion,
                Citation,
                CommunityReply,
                IngestionJob,
                ResearchMessage,
                ResearchSession,
                BundleItem,
                BundleSection,
                FilingBundle,
                Document,
                Draft,
                Task,
                Hearing,
                Note,
                CommunityPost,
                KnowledgeCollection,
                Case,
                Client,
            ):
                if hasattr(model, "owner_id"):
                    db.execute(delete(model).where(model.owner_id == owner))
            db.execute(delete(Session).where(Session.user_id == owner))
            db.execute(delete(AIConversation).where(AIConversation.user_id == owner))
            db.execute(delete(CommunityTag))
            db.execute(text("DELETE FROM rate_buckets"))
            db.execute(
                delete(User).where(User.email.in_(["researcher@tantara.local", "staff@tantara.local"]))
            )
            for stored in paths:
                path = Path(stored)
                if path.parent == (s.data_dir / "uploads").resolve():
                    path.unlink(missing_ok=True)
            shutil.rmtree(s.data_dir / "demo-fixtures", ignore_errors=True)
            db.flush()
            db.commit()
            from app.services.index_maintenance import rebuild_index

            print(
                "Empty typed workspace ready; local advocate account retained; vector index:",
                rebuild_index(),
            )
            return
        if db.scalar(select(func.count(Case.id)).where(Case.owner_id == owner, Case.is_demo.is_(True))):
            db.rollback()
            seed_junior_workspace()
            seed_community_workspace()
            with session_scope() as db:
                collections = ensure_demo_collections(db, owner)
                agreement_names = {"agreement.pdf", "contract.pdf", "near-duplicate-agreement-a.pdf", "near-duplicate-agreement-b.pdf"}
                authority_names = {"award.pdf"}
                for document in db.scalars(
                    select(Document).where(Document.owner_id == owner, Document.is_demo.is_(True))
                ):
                    if document.filename in agreement_names:
                        document.collection_id = collections["Agreements & Contracts"]
                    elif document.filename in authority_names:
                        document.collection_id = collections["Awards & Authorities"]
                    else:
                        document.collection_id = collections["Pleadings & Evidence"]
            print("Demo workspace already seeded; researcher workspace reconciled.")
            return
        users = []
        for email, name, role in (
            ("researcher@tantara.local", "Mira Shah", "researcher"),
            ("staff@tantara.local", "Dev Patel", "staff"),
        ):
            u = db.scalar(select(User).where(User.email == email))
            if not u:
                u = User(
                    id=str(uuid.uuid4()),
                    name=name,
                    email=email,
                    password_hash=hash_password(s.tantara_admin_password),
                    role=role,
                    avatar_initials="".join(x[0] for x in name.split()),
                    title=role.title(),
                )
                db.add(u)
                db.flush()
            users.append(u)
        clients = []
        for name in (
            "ABC Pvt. Ltd.",
            "TechBuild Ltd.",
            "Global Traders",
            "Solaris Energy",
            "Apex Construction",
            "Meridian Ports",
        ):
            row = Client(
                id=str(uuid.uuid4()),
                owner_id=owner,
                name=name,
                organization=name,
                email="legal@" + name.lower().replace(" ", "").replace(".", "") + ".example",
                status="active",
                notes="Demo client",
                is_demo=True,
            )
            db.add(row)
            clients.append(row)
        clients.append(
            Client(
                id=str(uuid.uuid4()),
                owner_id=owner,
                name="No Active Matters Ltd.",
                organization="No Active Matters Ltd.",
                email="legal@noactivematters.example",
                status="active",
                notes="Demo client with no cases.",
                is_demo=True,
            )
        )
        db.add(clients[-1])
        db.flush()
        pairs = [
            ("ABC Pvt. Ltd. vs. XYZ Ltd.", "SIAC"),
            ("TechBuild vs. Metro Infra", "ICC"),
            ("Global Traders vs. Oceanic", "LCIA"),
            ("Solaris Energy vs. Volt India", "DIAC"),
            ("Apex Construction vs. State", "Ad hoc"),
            ("Meridian Ports vs. Eastern Shipping", "SIIA"),
            ("Orion Systems vs. Nova Data", "SIAC"),
            ("Cedar Infrastructure vs. Riverworks", "ICC"),
            ("BluePeak Energy vs. Gridline", "LCIA"),
            ("Vantage Retail vs. Northstar", "DIAC"),
            ("Pioneer Mining vs. Terra Materials", "ICC"),
            ("Crown Hotels vs. Summit Hospitality", "Ad hoc"),
        ]
        cases = []
        for i, (title, forum) in enumerate(pairs):
            claimant, respondent = title.split(" vs. ", 1)
            cid = str(uuid.uuid4())
            case = Case(
                id=cid,
                owner_id=owner,
                title=title,
                reference_number=f"ARB/2025/{i + 1:03}",
                claimant=claimant,
                respondent=respondent,
                client_id=clients[i % 6].id,
                forum=forum,
                seat="Mumbai, India",
                governing_law="Indian law",
                arbitration_agreement_details="Section 7 arbitration agreement",
                dispute_category=("Construction" if i % 2 else "Commercial"),
                claim_amount=1250000 + i * 50000,
                claim_currency="INR",
                status="closed" if i == len(pairs) - 1 else "pending" if i == 2 else "active",
                description="Sample arbitration matter for local demo only.",
                is_demo=True,
            )
            db.add(case)
            cases.append(case)
            db.add(
                CaseParticipant(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=cid,
                    name="Workspace Advocate",
                    party_role="counsel",
                    organization="TANTARA",
                    is_demo=True,
                )
            )
            db.add(
                CaseParticipant(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=cid,
                    name=claimant,
                    party_role="claimant",
                    is_demo=True,
                )
            )
            due = datetime.combine(date.today() + timedelta(days=i - 3), datetime.min.time())
            db.add(
                Task(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=cid,
                    title="Review pleadings and evidence",
                    notes="Demo task.",
                    due_at=due,
                    priority=("high" if i % 3 == 0 else "medium"),
                    status="todo",
                    assignee="Workspace Advocate",
                    is_demo=True,
                )
            )
            db.add(
                Note(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=cid,
                    title="Initial review",
                    body="Demo note. Confirm all matter details against source records.",
                    kind="case_note",
                    is_demo=True,
                )
            )
            if i < 7:
                at = datetime.combine(date.today() + timedelta(days=i - 3), datetime.min.time()).replace(
                    hour=10
                )
                db.add(
                    Hearing(
                        id=str(uuid.uuid4()),
                        owner_id=owner,
                        case_id=cid,
                        title="Procedural hearing",
                        at=at,
                        mode="online",
                        forum=forum,
                        status="scheduled",
                        notes="Demo calendar item.",
                        is_demo=True,
                    )
                )
            if i == 1:
                for offset in (14, 28):
                    db.add(
                        Hearing(
                            id=str(uuid.uuid4()),
                            owner_id=owner,
                            case_id=cid,
                            title="Future case conference",
                            at=datetime.combine(
                                date.today() + timedelta(days=offset), datetime.min.time()
                            ).replace(hour=11),
                            mode="online",
                            forum=forum,
                            status="scheduled",
                            notes="Demo future hearing.",
                            is_demo=True,
                        )
                    )
            for event_type, offset, detail in (
                ("filed", -30 + i % 15, "Statement of claim filed"),
                ("first_hearing", -5 + i % 10, "Procedural hearing"),
                ("document_uploaded", -2 + i % 7, "Evidence bundle uploaded"),
                ("deadline_set", 12 + i % 20, "Reply submissions deadline"),
                ("all_day_event", i % 10, "All-day case preparation block"),
            ):
                db.add(
                    CaseEvent(
                        id=str(uuid.uuid4()),
                        owner_id=owner,
                        case_id=cid,
                        type=event_type,
                        occurred_at=datetime.combine(
                            date.today() + timedelta(days=offset), datetime.min.time()
                        ),
                        detail=detail,
                        is_demo=True,
                    )
                )
            if i % 4 == 0:
                db.add(
                    Task(
                        id=str(uuid.uuid4()),
                        owner_id=owner,
                        case_id=cid,
                        title="Unscheduled evidence review",
                        notes="Open task without a due date.",
                        due_at=None,
                        priority="medium",
                        status="todo",
                        assignee="Workspace Advocate",
                        is_demo=True,
                    )
                )
        for title, due in (
            ("Overdue filing review", date.today() - timedelta(days=2)),
            ("Due today: verify authorities", date.today()),
        ):
            db.add(
                Task(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    case_id=cases[0].id,
                    title=title,
                    due_at=datetime.combine(due, datetime.min.time()),
                    priority="high",
                    status="todo",
                    is_demo=True,
                )
            )
        db.flush()
        data_dir = s.data_dir
        fixture_dir = data_dir / "demo-fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        specs = [
            (
                "agreement.pdf",
                "Arbitration Agreement",
                [
                    "Arbitration agreement",
                    "Section 7 of the Arbitration and Conciliation Act, 1996. The parties agree to submit disputes arising from this contract to arbitration seated in Mumbai, India.",
                ],
            ),
            (
                "award.pdf",
                "Arbitral Award",
                [
                    "Sample arbitral award",
                    "This locally generated demo award records a hypothetical award dated 14 January 2025. It is not a real case, authority, or legal source.",
                ],
            ),
            (
                "contract.pdf",
                "Construction Contract",
                [
                    "Sample construction contract",
                    "The parties agree on project milestones, payment terms, notice obligations, and dispute resolution by arbitration. The force majeure clause addresses supply chain delay, extraordinary interruption, and resulting damages.",
                ],
                True,
            ),
            (
                "page-three-motion.pdf",
                "Page Three Motion",
                [
                    "Routine procedural filing and statement of the parties.",
                    "The contract describes notice and payment obligations.",
                    "Unique page three clause: Sapphire Pavilion shall host the special procedural conference on the third calendar day.",
                    "A procedural schedule shall be agreed by counsel.",
                    "The filing confirms the parties reserve their rights.",
                ],
            ),
            (
                "near-duplicate-agreement-a.pdf",
                "Near Duplicate Arbitration Agreement A",
                [
                    "The parties agree to arbitration seated in Mumbai, India under the applicable agreement. Aster notice applies.",
                ],
            ),
            (
                "near-duplicate-agreement-b.pdf",
                "Near Duplicate Arbitration Agreement B",
                [
                    "The parties agree to arbitration seated in Mumbai, India under the applicable agreement. Birch notice applies.",
                ],
            ),
            (
                "unique-term-evidence.pdf",
                "Unique Term Evidence",
                [
                    "ZXQORBITKEY appears only in this document and identifies a local demonstration record.",
                ],
            ),
        ]
        files = []
        for spec in specs:
            name, title, paragraphs, *options = spec
            path = fixture_dir / name
            make_pdf(path, title, paragraphs, *(options or [False]))
            files.append((name, title, path.read_bytes()))
        scanned = fixture_dir / "scanned-agreement.pdf"
        make_scanned_pdf(scanned)
        files.append(
            (
                "scanned-agreement.pdf",
                "Scanned Arbitration Agreement",
                scanned.read_bytes(),
            )
        )
        bundle = FilingBundle(
            id=str(uuid.uuid4()),
            owner_id=owner,
            case_id=cases[0].id,
            name="ABC Arbitration Filing Bundle",
            settings={
                "cover_page": True,
                "index": True,
                "synopsis": True,
                "list_of_dates": True,
            },
            status="draft",
            is_demo=True,
        )
        db.add(bundle)
        research = ResearchSession(
            id=str(uuid.uuid4()),
            owner_id=owner,
            title="Section 7 agreement review",
            case_id=cases[0].id,
            is_demo=True,
        )
        db.add(research)
        posts = []
        for post_index in range(5):
            post = CommunityPost(
                id=str(uuid.uuid4()),
                owner_id=owner,
                title=f"Demo: case practice discussion {post_index + 1}",
                body="Sample workspace discussion. Replace with your team's own notes and questions.",
                kind="question" if post_index % 2 else "discussion",
                visibility="workspace" if post_index == 0 else "private",
                tags=[cases[post_index].dispute_category.lower(), "procedure"],
                case_ref=cases[post_index].id,
                is_demo=True,
            )
            db.add(post)
            posts.append(post)
        db.flush()
        for post_index, post in enumerate(posts):
            for _ in range(2 if post_index < 3 else 1):
                db.add(
                    CommunityReply(
                        id=str(uuid.uuid4()),
                        owner_id=owner,
                        post_id=post.id,
                        body="Demo reply with a procedural note.",
                        is_demo=True,
                    )
                )
        draft = Draft(
            id=str(uuid.uuid4()),
            owner_id=owner,
            case_id=cases[0].id,
            title="Statement of Claim Outline",
            document_type="Statement of Claim",
            status="draft",
            content_markdown="# Statement of Claim\n\n[REVIEW: Replace every placeholder with verified case facts and supported legal submissions.]\n",
            is_demo=True,
        )
        db.add(draft)
        db.flush()
        db.add(
            DraftVersion(
                id=str(uuid.uuid4()),
                owner_id=owner,
                draft_id=draft.id,
                version_number=1,
                content_markdown=draft.content_markdown,
                change_note="Demo outline",
                is_demo=True,
            )
        )
        db.flush()
        case_id = cases[0].id
        collections = ensure_demo_collections(db, owner)
        agreement_names = {"agreement.pdf", "contract.pdf", "near-duplicate-agreement-a.pdf", "near-duplicate-agreement-b.pdf"}
        authority_names = {"award.pdf"}
        bundle_id = bundle.id
        docs = []
        for order, (filename, title, blob) in enumerate(files):
            did, jid = str(uuid.uuid4()), str(uuid.uuid4())
            digest = __import__("hashlib").sha256(blob).hexdigest()
            stored = __import__("app.ingestion", fromlist=["DocumentStorage"]).DocumentStorage().save(blob)
            collection_name = (
                "Agreements & Contracts"
                if filename in agreement_names
                else "Awards & Authorities"
                if filename in authority_names
                else "Pleadings & Evidence"
            )
            doc = Document(
                id=did,
                owner_id=owner,
                case_id=case_id,
                collection_id=collections[collection_name],
                title=title,
                document_type="Arbitration Agreement" if "Agreement" in title else title,
                jurisdiction="India",
                filename=filename,
                stored_path=stored,
                content_hash=digest,
                status="queued",
                is_demo=True,
            )
            db.add(doc)
            db.flush()
            db.add(
                IngestionJob(
                    id=jid,
                    owner_id=owner,
                    document_id=did,
                    status="queued",
                    steps=[],
                    warnings=[],
                    is_demo=True,
                )
            )
            db.add(
                BundleItem(
                    id=str(uuid.uuid4()),
                    owner_id=owner,
                    bundle_id=bundle_id,
                    document_id=did,
                    section="Core Documents",
                    order=order,
                    is_demo=True,
                )
            )
            docs.append((did, jid, filename, blob))
        db.flush()
        session_id = research.id
    for did, jid, filename, blob in docs:
        process_job(did, jid, owner, blob, filename)
    seed_junior_workspace()
    seed_community_workspace()
    with session_scope() as db:
        for did, _jid, filename, _blob in docs:
            fields = (
                [
                    ("agreement_date", "2025-01-14"),
                    ("seat", "Mumbai, India"),
                    ("document_type", "Arbitration Agreement"),
                ]
                if "agreement" in filename
                else [("document_title", filename.removesuffix(".pdf"))]
            )
            for key, value in fields:
                db.add(
                    ExtractionField(
                        id=str(uuid.uuid4()),
                        owner_id=owner,
                        document_id=did,
                        key=key,
                        value={"value": value, "page_number": 1},
                        provenance="extracted_reviewed",
                        source=filename,
                        review_required=True,
                        is_demo=True,
                    )
                )
    from app.routers.bundles import generate as generate_bundle

    generated = generate_bundle(bundle_id, {"id": owner, "role": "advocate", "name": "Workspace Advocate"})
    with session_scope() as db:
        session = db.get(ResearchSession, session_id)
        db.add(
            ResearchMessage(
                id=str(uuid.uuid4()),
                owner_id=owner,
                session_id=session.id,
                role="assistant",
                content="Demo session initialized. Ask a question to search the locally indexed fixture files.",
                status="ok",
                model={"provider": "local"},
                is_demo=True,
            )
        )
    print(
        f"Seeded {len(clients)} clients, {len(cases)} cases, {len(docs)} generated/indexed PDFs; bundle has {generated.get('pages')} pages."
    )


if __name__ == "__main__":
    main()
