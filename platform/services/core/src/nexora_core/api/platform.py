"""/v1/platform: the platform owner creates and lists organizations."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from nexora_core.api.deps import Conn, Now
from nexora_core.audit import record
from nexora_core.authz.require import require_platform
from nexora_core.ids import new_id
from nexora_core.tenancy.invitations import create_and_email

router = APIRouter(prefix="/v1/platform")
PlatformOwner = Annotated[str, Depends(require_platform("platform:organizations"))]
SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NewOrganization(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str
    owner_email: str = Field(max_length=320)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.fullmatch(value):
            raise ValueError(
                "2-63 lowercase letters, digits or hyphens, not starting or ending with a hyphen"
            )
        return value

    @field_validator("owner_email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not EMAIL.fullmatch(value):
            raise ValueError("not an email address")
        return value


@router.get("/organizations")
async def list_organizations(_owner: PlatformOwner, conn: Conn) -> dict:
    rows = await conn.execute(text("SELECT * FROM nexora_platform_organizations() ORDER BY name"))
    return {"items": [dict(r) for r in rows.mappings()]}


@router.post("/organizations", status_code=201)
async def create_organization(
    body: NewOrganization, owner_id: PlatformOwner, conn: Conn, at: Now, request: Request
) -> dict:
    org_id, ws_id = new_id("org"), new_id("ws")
    await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org_id})
    try:
        async with conn.begin_nested():
            await conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_at, updated_at)"
                    " VALUES (:i, :n, :s, :now, :now)"
                ),
                {"i": org_id, "n": body.name, "s": body.slug, "now": at},
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="slug_taken") from exc
    await conn.execute(
        text(
            "INSERT INTO workspaces (id, organization_id, name, slug, environment, created_at, updated_at)"
            " VALUES (:i, :o, 'Production', 'production', 'production', :now, :now)"
        ),
        {"i": ws_id, "o": org_id, "now": at},
    )
    invitation = await create_and_email(
        conn,
        request.app.state.mailer,
        organization_id=org_id,
        email=body.owner_email,
        role="org_owner",
        invited_by=owner_id,
        now=at,
        public_url=request.app.state.settings.public_url,
    )
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    async def audit(action: str, target_type: str, target_id: str, *, details: dict | None = None) -> None:
        await record(
            conn,
            organization_id=org_id,
            actor_type="user",
            actor_id=owner_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            workspace_id=ws_id if target_type == "workspace" else None,
            details=details,
            ip=ip,
            user_agent=user_agent,
        )

    await audit("organization.created", "organization", org_id)
    await audit("workspace.created", "workspace", ws_id, details={"environment": "production"})
    await audit(
        "invitation.created",
        "invitation",
        invitation["id"],
        details={"role": "org_owner", "scope": "organization"},
    )
    return {
        "id": org_id,
        "name": body.name,
        "slug": body.slug,
        "workspace": {"id": ws_id, "name": "Production", "environment": "production"},
        "invitation": {
            "id": invitation["id"],
            "email": invitation["email"],
            "role": invitation["role_key"],
            "expires_at": invitation["expires_at"],
        },
    }
