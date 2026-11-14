"""/v1/organizations: mine, read, update, audit log."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from nexora_core.api.deps import Conn, CurrentSession, Now
from nexora_core.audit import record
from nexora_core.authz.require import Principal, require

router = APIRouter(prefix="/v1")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


@router.get("/organizations")
async def my_organizations(session: CurrentSession, conn: Conn) -> dict:
    rows = await conn.execute(
        text("SELECT * FROM nexora_user_organizations(:u) ORDER BY name"), {"u": session.user_id}
    )
    return {"items": [dict(r) for r in rows.mappings()]}


@router.get("/organizations/{org}")
async def get_organization(
    principal: Annotated[Principal, Depends(require("organization:read"))], conn: Conn
) -> dict:
    row = (
        (
            await conn.execute(
                text(
                    "SELECT id, name, slug, status, data_region, created_at FROM organizations WHERE id = :o"
                ),
                {"o": principal.organization_id},
            )
        )
        .mappings()
        .one()
    )
    return {**row, "permissions": sorted(principal.permissions)}


@router.patch("/organizations/{org}")
async def update_organization(
    body: OrganizationUpdate,
    principal: Annotated[Principal, Depends(require("organization:update"))],
    conn: Conn,
    at: Now,
    request: Request,
) -> dict:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        await conn.execute(
            text("UPDATE organizations SET name = :name, updated_at = :now WHERE id = :o"),
            {"name": changes["name"], "now": at, "o": principal.organization_id},
        )
        await record(
            conn,
            organization_id=principal.organization_id,
            actor_type="user",
            actor_id=principal.user_id,
            action="organization.updated",
            target_type="organization",
            target_id=principal.organization_id,
            details={"fields": sorted(changes)},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    row = (
        (
            await conn.execute(
                text("SELECT id, name, slug FROM organizations WHERE id = :o"),
                {"o": principal.organization_id},
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


@router.get("/organizations/{org}/audit-logs")
async def audit_logs(
    principal: Annotated[Principal, Depends(require("audit:read"))],
    conn: Conn,
    before: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    rows = await conn.execute(
        text(
            "SELECT id, occurred_at, actor_type, actor_id, action, target_type, target_id, workspace_id,"
            " details FROM audit_logs WHERE organization_id = :o"
            " AND (CAST(:before AS bigint) IS NULL OR id < :before)"
            " ORDER BY id DESC LIMIT :limit"
        ),
        {"o": principal.organization_id, "before": before, "limit": limit},
    )
    items = [dict(r) for r in rows.mappings()]
    return {"items": items, "next_before": items[-1]["id"] if len(items) == limit else None}
