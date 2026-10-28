#!/usr/bin/env python3
"""Probe and index a small, verifiable arbitration corpus; never scrape in bulk."""

import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
from app.config import get_settings
from app.db import SessionLocal, init_db, session_scope
from app.ingestion import DocumentStorage
from app.models import Document, IngestionJob, User
from app.routers.documents import process_job
from sqlalchemy import select

SOURCES = [
    {
        "url": "https://en.wikisource.org/wiki/Arbitration_and_Conciliation_Act,_1996",
        "publisher": "Wikisource contributors",
        "title": "Arbitration and Conciliation Act, 1996 (Wikisource transcription)",
        "doc_date": "1996",
        "jurisdiction": "India",
        "doc_type": "statute",
        "license": "Wikisource transcription; public-domain source text hosted by a mirror. Verify against the official edition; this is not an official copy.",
        "kind": "mirror",
    },
    {
        "url": "https://uncitral.un.org/en/texts/arbitration",
        "publisher": "United Nations Commission on International Trade Law",
        "title": "UNCITRAL Arbitration and Conciliation",
        "doc_date": None,
        "jurisdiction": "International",
        "doc_type": "institutional guidance",
        "license": "Official UN webpage; copyright and reuse terms remain with the publisher.",
        "kind": "official",
    },
    {
        "url": "https://www.lcia.org/Dispute_Resolution_Services/LCIA_Arbitration_Rules.aspx",
        "publisher": "London Court of International Arbitration",
        "title": "LCIA Arbitration Rules",
        "doc_date": "2020",
        "jurisdiction": "International",
        "doc_type": "institutional rules",
        "license": "Official LCIA webpage; copyright and reuse terms remain with LCIA.",
        "kind": "official",
    },
]
UNREACHABLE = [
    {
        "url": "https://www.indiacode.nic.in/",
        "publisher": "India Code",
        "title": "Official legislation portal probe",
        "kind": "official",
    },
    {
        "url": "https://main.sci.gov.in/",
        "publisher": "Supreme Court of India",
        "title": "Official court portal probe",
        "kind": "official",
    },
    {
        "url": "https://static.siac.org/",
        "publisher": "SIAC",
        "title": "Institution portal probe",
        "kind": "official",
    },
    {
        "url": "https://archive.org/",
        "publisher": "Internet Archive",
        "title": "Archive mirrors probe",
        "kind": "mirror",
    },
]


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def extract_text(raw):
    p = TextOnly()
    p.feed(raw.decode("utf-8", errors="replace"))
    return "\n".join(p.parts)[:250000]


def check_robots(client, url, agent):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = client.get(robots_url)
    if response.status_code == 404:
        return
    response.raise_for_status()
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(agent, url):
        raise PermissionError("robots.txt disallows this URL")


def main():
    init_db()
    settings = get_settings()
    directory = settings.data_dir / "corpus"
    originals = directory / "originals"
    derived = directory / "derived"
    originals.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    agent = "TANTARA-local-corpus-import/1.0 (single-page, user initiated)"
    report = []
    targets = SOURCES + UNREACHABLE
    with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": agent}) as client:
        for source in targets:
            item = {
                **source,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source_url": source["url"],
            }
            try:
                check_robots(client, source["url"], agent)
                response = client.get(source["url"])
                response.raise_for_status()
                if len(response.content) > 8_000_000:
                    raise ValueError("Source exceeds 8 MB single-document limit")
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and not response.content.lstrip().startswith(
                    (b"<!DOCTYPE", b"<html", b"<HTML")
                ):
                    raise ValueError("Expected an HTML publication page")
                text = extract_text(response.content)
                if len(text.strip()) < 100:
                    raise ValueError("Response did not contain enough readable source text")
                digest = hashlib.sha256(response.content).hexdigest()
                original = originals / (digest + ".html")
                original.write_bytes(response.content)
                plain = text.encode("utf-8")
                text_hash = hashlib.sha256(plain).hexdigest()
                text_path = derived / (text_hash + ".txt")
                text_path.write_bytes(plain)
                with SessionLocal() as s:
                    owner = s.scalar(select(User).where(User.email == "advocate@tantara.local"))
                if owner is None:
                    raise RuntimeError("Local advocate account is not initialized")
                with SessionLocal() as s:
                    existing = s.scalar(
                        select(Document).where(
                            Document.owner_id == owner.id,
                            Document.content_hash == text_hash,
                        )
                    )
                if existing:
                    item.update(
                        status="already_indexed",
                        document_id=existing.id,
                        sha256=digest,
                        stored_original=str(original.relative_to(settings.data_dir)),
                    )
                else:
                    did, jid = str(uuid.uuid4()), str(uuid.uuid4())
                    stored = DocumentStorage().save(plain)
                    with session_scope() as s:
                        s.add(
                            Document(
                                id=did,
                                owner_id=owner.id,
                                title=source["title"],
                                document_type=source["doc_type"],
                                jurisdiction=source["jurisdiction"],
                                source_label=source["publisher"],
                                source_url=source["url"],
                                publisher=source["publisher"],
                                official_title=source["title"],
                                doc_date=source.get("doc_date"),
                                retrieved_at=datetime.now(UTC).replace(tzinfo=None),
                                license_note=source["license"],
                                citation_metadata={
                                    "source_kind": source["kind"],
                                    "original_sha256": digest,
                                    "original_path": str(original.relative_to(settings.data_dir)),
                                    "derived_sha256": text_hash,
                                },
                                filename=source["title"][:180] + ".txt",
                                stored_path=stored,
                                content_hash=text_hash,
                                status="queued",
                            )
                        )
                        s.add(
                            IngestionJob(
                                id=jid,
                                owner_id=owner.id,
                                document_id=did,
                                status="queued",
                                steps=[],
                                warnings=[],
                            )
                        )
                    process_job(did, jid, owner.id, plain, source["title"] + ".txt")
                    with SessionLocal() as s:
                        doc = s.get(Document, did)
                        state = doc.status if doc else "failed"
                    item.update(
                        status="indexed" if state == "ready" else "failed",
                        document_id=did,
                        sha256=digest,
                        stored_original=str(original.relative_to(settings.data_dir)),
                        derived_sha256=text_hash,
                        license_note=source["license"],
                    )
                    if state != "ready":
                        item["reason"] = "Document processing did not reach ready state"
            except Exception as exc:
                reason = str(exc).strip() or type(exc).__name__
                item.update(status="failed", reason=f"{type(exc).__name__}: {reason[:240]}")
                if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                    item["reason"] = "Connection failure: source was unreachable from this host"
            report.append(item)
            print(
                json.dumps(
                    {
                        "url": item["url"],
                        "status": item["status"],
                        "reason": item.get("reason"),
                    }
                ),
                flush=True,
            )
    manifest = {
        "status": "complete",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "items": report,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
