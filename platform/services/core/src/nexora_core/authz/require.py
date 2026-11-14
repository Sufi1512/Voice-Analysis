"""Per-request authorization: ``Depends(require("member:invite"))`` on a route with ``{org}``.

Order (DB doc §3.2): platform owner → organization role → workspace membership; deny by
default. The request transaction gets ``nexora.org_id`` set *before* any tenant query, so
row-level security scopes everything the handler does. A user who is not a member gets 404
whether or not the organization exists.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import text

from nexora_core.api.deps import Conn, CurrentSession
from nexora_core.authz.catalogue import PERMISSIONS, ROLE_PERMISSIONS, WORKSPACE_MEMBER_PERMISSIONS

NOT_FOUND = HTTPException(status_code=404, detail={"error": "not_found"})


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    is_platform_owner: bool
    permissions: frozenset[str]
    #: Roles held for the whole organization (workspace-only memberships excluded).
    org_roles: frozenset[str] = frozenset()


def _effective(memberships: list[tuple[str, str | None]]) -> frozenset[str]:
    granted: set[str] = set()
    for role, workspace_id in memberships:
        granted |= ROLE_PERMISSIONS[role] if workspace_id is None else WORKSPACE_MEMBER_PERMISSIONS
    return frozenset(granted)


def require(permission: str) -> Callable[..., Awaitable[Principal]]:
    if permission not in PERMISSIONS:
        raise ValueError(f"unknown permission {permission!r}")

    async def dependency(org: str, session: CurrentSession, conn: Conn) -> Principal:
        await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org})
        exists = await conn.scalar(
            text("SELECT 1 FROM organizations WHERE id = :o AND status = 'active'"), {"o": org}
        )
        is_platform_owner = bool(
            await conn.scalar(
                text("SELECT is_platform_owner FROM users WHERE id = :u"), {"u": session.user_id}
            )
        )
        rows = (
            await conn.execute(
                text("SELECT role_key, workspace_id FROM memberships WHERE user_id = :u"),
                {"u": session.user_id},
            )
        ).all()
        if not exists or (not rows and not is_platform_owner):
            raise NOT_FOUND
        granted = _effective([(r, w) for r, w in rows])
        if not is_platform_owner and permission not in granted:
            raise HTTPException(
                status_code=403, detail={"error": "forbidden", "missing_permission": permission}
            )
        org_roles = frozenset(r for r, w in rows if w is None)
        return Principal(session.user_id, org, is_platform_owner, granted, org_roles)

    dependency.permission = permission  # ty: ignore[missing-attribute] - read by route_permission
    return dependency


def require_platform(permission: str) -> Callable[..., Awaitable[str]]:
    """For /v1/platform routes: only the platform owner; returns their user id."""
    if permission not in ROLE_PERMISSIONS["platform_owner"]:
        raise ValueError(f"{permission!r} is not a platform permission")

    async def dependency(session: CurrentSession, conn: Conn) -> str:
        owner = await conn.scalar(
            text("SELECT is_platform_owner FROM users WHERE id = :u"), {"u": session.user_id}
        )
        if not owner:
            raise HTTPException(
                status_code=403, detail={"error": "forbidden", "missing_permission": permission}
            )
        return session.user_id

    dependency.permission = permission  # ty: ignore[missing-attribute] - read by route_permission
    return dependency


def route_permission(route: APIRoute) -> str | None:
    """The permission a route requires, for the endpoint-by-role matrix test."""
    for dep in route.dependant.dependencies:
        perm: Any = getattr(dep.call, "permission", None)
        if isinstance(perm, str):
            return perm
    return None
