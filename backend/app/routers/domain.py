"""Typed paginated CRUD routes for clients, cases, hearings, tasks, drafts, and bundles."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, exists, func, select

from app.db import SessionLocal, session_scope
from app.models import *
from app.repositories.domain import (
    ENTITY_MODELS,
    fields_for,
    get_owned,
    list_owned,
    serialize,
)
from app.repositories.domain import (
    create as repo_create,
)
from app.repositories.domain import (
    update as repo_update,
)
from app.schemas import CREATE_SCHEMAS, PATCH_SCHEMAS
from app.security import current_user
from app.services.audit import record
from app.services.draft_versions import snapshot_draft
from app.storage_paths import stored_path
from app.timezone import to_workspace_iso, to_workspace_naive, workspace_now

router = APIRouter(prefix="/api/v1")


class Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


def owned(session, cls, rid, user):
    item = get_owned(session, cls, rid, user["id"])
    if item is None:
        raise HTTPException(404, "Record not found")
    return item


def assert_write_role(user, cls):
    role = user.get("role")
    if role == "researcher":
        raise HTTPException(403, "This role is read-only")
    if role == "staff" and cls in {Client, Case, Draft, FilingBundle, CommunityPost}:
        raise HTTPException(403, "This role cannot modify this resource")


def list_domain(cls, user, **kwargs):
    with SessionLocal() as s:
        return list_owned(s, cls, user["id"], **kwargs)


def visible_community_post(session, post_id, user_id):
    return session.scalar(
        select(CommunityPost).where(
            CommunityPost.id == post_id,
            (CommunityPost.owner_id == user_id) | (CommunityPost.visibility == "workspace"),
        )
    )


def add_community_author(session, item):
    author = session.get(User, item.get("owner_id"))
    if author:
        item["author"] = {"display_name": author.name, "role": author.role}
        item["author_name"] = author.name
        item["author_role"] = author.role
    return item


def add_derived_fields(session, cls, item, owner_id):
    if cls is Client:
        item["case_count"] = (
            session.scalar(
                select(func.count(Case.id)).where(
                    Case.owner_id == owner_id,
                    Case.client_id == item["id"],
                    Case.status != "archived",
                )
            )
            or 0
        )
    if cls is Case:
        next_hearing = session.scalar(
            select(func.min(Hearing.at)).where(
                Hearing.owner_id == owner_id,
                Hearing.case_id == item["id"],
                Hearing.at >= workspace_now().replace(tzinfo=None),
            )
        )
        item["next_hearing_at"] = to_workspace_iso(next_hearing) if next_hearing else None
    return item


def register_crud(path, cls):
    async def listing(
        q: str | None = None,
        status: str | None = None,
        case_id: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        sort: str = "created_at",
        from_: str | None = Query(None, alias="from"),
        to: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        saved: bool | None = None,
        user=Depends(current_user),
    ):
        filters = []
        if cls is Hearing:
            try:
                if from_:
                    filters.append(
                        Hearing.at
                        >= to_workspace_naive(datetime.fromisoformat(from_.replace("Z", "+00:00")))
                    )
                if to:
                    filters.append(
                        Hearing.at <= to_workspace_naive(datetime.fromisoformat(to.replace("Z", "+00:00")))
                    )
            except ValueError:
                raise HTTPException(400, "from and to must be ISO dates")
        if cls is CommunityPost:
            from app.models import SavedItem

            if kind:
                filters.append(CommunityPost.kind == kind)
            if tag:
                filters.append(CommunityPost.tags.cast(String).like(f'%"{tag}"%'))
            if saved is True:
                filters.append(
                    exists(
                        select(SavedItem.id).where(
                            SavedItem.owner_id == user["id"],
                            SavedItem.item_type == "community_post",
                            SavedItem.item_id == CommunityPost.id,
                        )
                    )
                )
            if saved is False:
                filters.append(
                    ~exists(
                        select(SavedItem.id).where(
                            SavedItem.owner_id == user["id"],
                            SavedItem.item_type == "community_post",
                            SavedItem.item_id == CommunityPost.id,
                        )
                    )
                )
        with SessionLocal() as s:
            if cls is CommunityPost and sort == "created_at":
                sort = "-created_at"
            result = list_owned(
                s,
                cls,
                user["id"],
                q=q,
                status=status,
                case_id=case_id,
                page=page,
                page_size=page_size,
                sort=sort,
                extra_filters=filters,
                include_workspace=cls is CommunityPost,
            )
            for item in result["items"]:
                add_derived_fields(s, cls, item, user["id"])
                if cls is CommunityPost:
                    add_community_author(s, item)
                for key in ("owner_id", "output_path", "stored_path", "text_content", "embedding_blob"):
                    item.pop(key, None)
                if cls is FilingBundle:
                    bundle_row = s.get(FilingBundle, item["id"])
                    case_row = (
                        s.scalar(select(Case).where(Case.id == bundle_row.case_id, Case.owner_id == user["id"]))
                        if bundle_row and bundle_row.case_id
                        else None
                    )
                    from app.routers.bundles import _items

                    bundle_items = _items(s, bundle_row, user) if bundle_row else []
                    sections = (
                        s.scalars(
                            select(BundleSection)
                            .where(BundleSection.bundle_id == item["id"], BundleSection.owner_id == user["id"])
                            .order_by(BundleSection.order)
                        ).all()
                        if bundle_row
                        else []
                    )
                    section_titles = {
                        section.title.strip()
                        for section in sections
                        if section.title and section.title.strip()
                    }
                    section_titles.update(
                        entry["section"].strip()
                        for entry in bundle_items
                        if entry.get("section") and entry["section"].strip()
                    )
                    settings = item.get("settings") or {}
                    front_pages = sum(
                        settings.get(key, True) for key in ("cover_page", "index", "synopsis", "list_of_dates")
                    )
                    item["case_title"] = case_row.title if case_row else None
                    item["section_count"] = len(section_titles)
                    item["page_count"] = front_pages + sum(entry["pages"] for entry in bundle_items)
                    try:
                        output = stored_path("bundles", bundle_row.output_path) if bundle_row and bundle_row.output_path else None
                    except ValueError:
                        output = None
                    item["downloadable"] = bool(output and output.is_file())
                    item["file_size_bytes"] = output.stat().st_size if output and output.is_file() else None
                    item["download_url"] = (
                        f"/api/v1/bundles/{item['id']}/download" if item["downloadable"] else None
                    )
            return result

    def create(payload: Payload, user=Depends(current_user)):
        if cls is not CommunityPost:
            assert_write_role(user, cls)
        values = payload.model_dump(exclude_unset=True)
        allowed = fields_for(cls) - {"id", "created_at", "updated_at", "owner_id", "is_demo"}
        if cls is FilingBundle:
            allowed.discard("output_path")
        values = {k: v for k, v in values.items() if k in allowed}
        if cls is Case and values.get("client_id"):
            with SessionLocal() as s:
                owned(s, Client, values["client_id"], user)
        if cls is CommunityPost and values.get("case_ref"):
            with SessionLocal() as s:
                owned(s, Case, values["case_ref"], user)
        if values.get("case_id"):
            with SessionLocal() as s:
                owned(s, Case, values["case_id"], user)
        with session_scope() as s:
            row = repo_create(s, cls, user["id"], values)
            record(s, user["id"], "create", cls.__tablename__, row.id)
            result = serialize(row)
            if cls is CommunityPost:
                add_community_author(s, result)
                result.pop("owner_id", None)
            return result

    def get(rid: str, user=Depends(current_user)):
        with SessionLocal() as s:
            row = (
                visible_community_post(s, rid, user["id"])
                if cls is CommunityPost
                else owned(s, cls, rid, user)
            )
            if row is None:
                raise HTTPException(404, "Record not found")
            out = serialize(row)
            add_derived_fields(s, cls, out, user["id"])
            if cls is CommunityPost:
                add_community_author(s, out)
            for key in ("owner_id", "output_path", "stored_path", "text_content", "embedding_blob"):
                out.pop(key, None)
            if cls is FilingBundle:
                try:
                    output = stored_path("bundles", row.output_path) if row.output_path else None
                except ValueError:
                    output = None
                out["downloadable"] = bool(output and output.is_file())
                out["download_url"] = f"/api/v1/bundles/{rid}/download" if out["downloadable"] else None
                from app.routers.bundles import _items

                items = _items(s, row, user)
                sections = s.scalars(
                    select(BundleSection)
                    .where(BundleSection.bundle_id == row.id, BundleSection.owner_id == user["id"])
                    .order_by(BundleSection.order)
                ).all()
                out["items"] = items
                out["sections"] = [{"title": section.title, "order": section.order} for section in sections]
                settings = row.settings or {}
                front_matter_pages = sum(
                    settings.get(key, True)
                    for key in ("cover_page", "index", "synopsis", "list_of_dates")
                )
                out["page_count"] = front_matter_pages + sum(item["pages"] for item in items)
            return out

    def patch(rid: str, payload: Payload, user=Depends(current_user)):
        if cls is not CommunityPost:
            assert_write_role(user, cls)
        values = payload.model_dump(exclude_unset=True)
        if cls is FilingBundle and "output_path" in values:
            raise HTTPException(400, "Bundle output paths are system managed")
        if values.get("case_id"):
            with SessionLocal() as s:
                owned(s, Case, values["case_id"], user)
        if cls is Case and values.get("client_id"):
            with SessionLocal() as s:
                owned(s, Client, values["client_id"], user)
        if cls is CommunityPost and values.get("case_ref"):
            with SessionLocal() as s:
                owned(s, Case, values["case_ref"], user)
        with session_scope() as s:
            row = owned(s, cls, rid, user)
            if cls is Draft and "content_markdown" in values:
                incoming = values["content_markdown"]
                if incoming is None:
                    values.pop("content_markdown")
                elif incoming != row.content_markdown:
                    snapshot_draft(s, row, row.content_markdown, "Edited in editor")
            repo_update(s, row, values)
            record(s, user["id"], "update", cls.__tablename__, rid)
            result = serialize(row)
            if cls is CommunityPost:
                add_community_author(s, result)
                result.pop("owner_id", None)
            return result

    def delete(rid: str, user=Depends(current_user)):
        assert_write_role(user, cls)
        with session_scope() as s:
            row = owned(s, cls, rid, user)
            if cls is Case:
                row.status = "archived"
                result = {"deleted": False, "archived": True}
            else:
                s.delete(row)
                result = {"deleted": True}
            record(s, user["id"], "delete", cls.__tablename__, rid)
            return result

    if path in CREATE_SCHEMAS:
        create.__annotations__["payload"] = CREATE_SCHEMAS[path]
        patch.__annotations__["payload"] = PATCH_SCHEMAS[path]
    router.add_api_route("/" + path, listing, methods=["GET"], name=path + "_list")
    router.add_api_route(
        "/" + path,
        create,
        methods=["POST"],
        name=path + "_create",
        status_code=201 if path == "cases" else 200,
    )
    router.add_api_route("/" + path + "/{rid}", get, methods=["GET"], name=path + "_get")
    router.add_api_route("/" + path + "/{rid}", patch, methods=["PATCH"], name=path + "_patch")
    router.add_api_route("/" + path + "/{rid}", delete, methods=["DELETE"], name=path + "_delete")


for route, model in ENTITY_MODELS.items():
    register_crud(route, model)
