"""Invite people (/v1/organizations/{org}/invitations) and accept (/v1/invitations/{token}/accept)."""

import re
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from nexora_core.api.deps import Conn, Now
from nexora_core.audit import record
from nexora_core.auth import throttle
from nexora_core.auth.csrf import COOKIE_MAX_AGE, SESSION_COOKIE, new_token, set_csrf_cookie
from nexora_core.auth.passwords import hash_password, verify_password
from nexora_core.auth.sessions import create_session, resolve_session
from nexora_core.authz.catalogue import ORGANIZATION_ONLY_ROLES, ROLE_RANK
from nexora_core.authz.require import Principal, require
from nexora_core.ids import new_id
from nexora_core.tenancy.invitations import DEFAULT_ROLE, create_and_email
from nexora_core.tokens import hash_token

if TYPE_CHECKING:
    from nexora_core.mail import Mailer

router = APIRouter(prefix="/v1")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 12
INVITABLE = frozenset(ROLE_RANK) - {"platform_owner"}


class NewInvitation(BaseModel):
    email: str = Field(max_length=320)
    role: str = DEFAULT_ROLE
    workspace_id: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not EMAIL.fullmatch(value):
            raise ValueError("not an email address")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in INVITABLE:
            raise ValueError(f"role must be one of {sorted(INVITABLE)}")
        return value

    def model_post_init(self, _context: object) -> None:
        if self.workspace_id is not None and self.role in ORGANIZATION_ONLY_ROLES:
            raise ValueError(f"{self.role} applies to the whole organization, not one workspace")


class Acceptance(BaseModel):
    password: str | None = Field(default=None, max_length=1024)
    name: str | None = Field(default=None, max_length=200)

    def __repr__(self) -> str:
        return "Acceptance(password=***)"


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


@router.post("/organizations/{org}/invitations", status_code=201)
async def invite(
    body: NewInvitation,
    principal: Annotated[Principal, Depends(require("member:invite"))],
    conn: Conn,
    at: Now,
    request: Request,
) -> dict:
    org = principal.organization_id
    inviter_rank = (
        100 if principal.is_platform_owner else max((ROLE_RANK[r] for r in principal.org_roles), default=0)
    )
    if ROLE_RANK[body.role] > inviter_rank:
        raise HTTPException(status_code=403, detail="role_too_high")
    if body.workspace_id is None and not (
        principal.is_platform_owner or "member:manage" in principal.permissions
    ):
        raise HTTPException(status_code=403, detail="workspace_required")
    if body.workspace_id is not None and not await conn.scalar(
        text("SELECT 1 FROM workspaces WHERE id = :w AND organization_id = :o"),
        {"w": body.workspace_id, "o": org},
    ):
        raise HTTPException(status_code=422, detail="unknown_workspace")
    if await conn.scalar(
        text(
            "SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id WHERE u.email = :e"
            " AND (m.workspace_id IS NULL OR m.workspace_id = :w)"
        ),
        {"e": body.email, "w": body.workspace_id},
    ):
        raise HTTPException(status_code=409, detail="already_member")
    await conn.execute(  # a new invitation replaces any pending one for the same person and scope
        text(
            "UPDATE invitations SET revoked_at = :now WHERE email = :e"
            " AND workspace_id IS NOT DISTINCT FROM :w AND accepted_at IS NULL AND revoked_at IS NULL"
        ),
        {"now": at, "e": body.email, "w": body.workspace_id},
    )
    mailer: Mailer = request.app.state.mailer
    row = await create_and_email(
        conn,
        mailer,
        organization_id=org,
        email=body.email,
        invited_by=principal.user_id,
        now=at,
        public_url=request.app.state.settings.public_url,
        role=body.role,
        workspace_id=body.workspace_id,
    )
    ip, ua = _client(request)
    await record(
        conn,
        organization_id=org,
        actor_type="user",
        actor_id=principal.user_id,
        action="invitation.created",
        target_type="invitation",
        target_id=row["id"],
        workspace_id=body.workspace_id,
        details={"role": body.role, "scope": "workspace" if body.workspace_id else "organization"},
        ip=ip,
        user_agent=ua,
    )
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role_key"],
        "workspace_id": row["workspace_id"],
        "expires_at": row["expires_at"],
    }


async def _accepting_user(
    conn: Conn, request: Request, invitation: dict, body: Acceptance, at: Now
) -> tuple[str, bool]:
    """Who accepts: (user id, whether a new session is needed). Raises on any mismatch."""
    user = (
        (
            await conn.execute(
                text("SELECT id, password_hash, status FROM users WHERE email = :e"),
                {"e": invitation["email"]},
            )
        )
        .mappings()
        .first()
    )
    raw = request.cookies.get(SESSION_COOKIE)
    session = await resolve_session(conn, raw, now=at) if raw else None
    if session is not None:
        if user is None or session.user_id != user["id"]:
            raise HTTPException(status_code=403, detail="invitation_for_another_account")
        return user["id"], False
    if user is not None:
        key = throttle.key(throttle.EMAIL, invitation["email"])
        if await throttle.locked_until(conn, [key], now=at):
            raise HTTPException(status_code=429, detail="locked")
        if user["status"] != "active" or not verify_password(user["password_hash"], body.password or ""):
            await throttle.record_failure(conn, key, throttle.EMAIL, now=at)
            raise HTTPException(status_code=401, detail="invalid_credentials")
        await conn.execute(
            text("UPDATE users SET email_verified_at = coalesce(email_verified_at, :now) WHERE id = :i"),
            {"now": at, "i": user["id"]},
        )
        return user["id"], True
    if body.password is None or len(body.password) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail="password_too_short")
    uid = new_id("usr")
    await conn.execute(
        text(
            "INSERT INTO users (id, email, name, password_hash, email_verified_at, created_at, updated_at)"
            " VALUES (:i, :e, :n, :h, :now, :now, :now)"
        ),
        {
            "i": uid,
            "e": invitation["email"],
            "n": (body.name or "").strip(),
            "h": hash_password(body.password),
            "now": at,
        },
    )
    return uid, True


@router.post("/invitations/{token}/accept", response_model=None)
async def accept(token: str, body: Acceptance, request: Request, conn: Conn, at: Now) -> JSONResponse:
    invitation = (
        (await conn.execute(text("SELECT * FROM nexora_invitation_by_token(:h)"), {"h": hash_token(token)}))
        .mappings()
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="invitation_invalid")
    if invitation["accepted_at"] is not None or invitation["revoked_at"] is not None:
        raise HTTPException(status_code=410, detail="invitation_used")
    if invitation["expires_at"] <= at:
        raise HTTPException(status_code=410, detail="invitation_expired")
    org = invitation["organization_id"]
    await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org})

    # Claim first: the row lock makes a racing acceptance wait, then find it used. Any later
    # refusal (wrong password, weak password) rolls the claim back with the transaction.
    claimed = await conn.scalar(  # single use, even when two acceptances race
        text(
            "UPDATE invitations SET accepted_at = :now WHERE id = :i AND accepted_at IS NULL"
            " AND revoked_at IS NULL AND expires_at > :now RETURNING id"
        ),
        {"now": at, "i": invitation["id"]},
    )
    if claimed is None:
        raise HTTPException(status_code=410, detail="invitation_used")
    user_id, needs_session = await _accepting_user(conn, request, dict(invitation), body, at)
    member_id = new_id("mem")
    await conn.execute(
        text(
            "INSERT INTO memberships (id, organization_id, user_id, workspace_id, role_key, created_at)"
            " VALUES (:i, :o, :u, :w, :r, :now) ON CONFLICT DO NOTHING"
        ),
        {
            "i": member_id,
            "o": org,
            "u": user_id,
            "w": invitation["workspace_id"],
            "r": invitation["role_key"],
            "now": at,
        },
    )
    ip, ua = _client(request)

    async def audit(action: str, target_type: str, target_id: str, details: dict | None = None) -> None:
        await record(
            conn,
            organization_id=org,
            actor_type="user",
            actor_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            workspace_id=invitation["workspace_id"],
            details=details,
            ip=ip,
            user_agent=ua,
        )

    await audit("invitation.accepted", "invitation", invitation["id"])
    await audit("member.added", "user", user_id, {"role": invitation["role_key"]})

    user = (
        (await conn.execute(text("SELECT id, email, name FROM users WHERE id = :i"), {"i": user_id}))
        .mappings()
        .one()
    )
    response = JSONResponse(
        content={
            "user": dict(user),
            "organization_id": org,
            "role": invitation["role_key"],
            "workspace_id": invitation["workspace_id"],
        }
    )
    if needs_session:
        raw = await create_session(conn, user_id=user_id, now=at, ip=ip, user_agent=ua)
        response.set_cookie(
            SESSION_COOKIE, raw, max_age=COOKIE_MAX_AGE, path="/", secure=True, httponly=True, samesite="lax"
        )
        set_csrf_cookie(response, new_token())
    return response
