"""C2: migrations run up and down (AC-8); tenant rows are isolated by row-level security (AC-1)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.db_harness import APP_ROLE, app_engine, downgrade, upgrade

TENANT_TABLES = ["workspaces", "memberships", "invitations", "audit_logs", "secrets"]


async def tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        names = {r[0] for r in rows}
    await engine.dispose()
    return names


async def test_migrations_up_and_down(migrated):
    assert {"organizations", "users", *TENANT_TABLES} <= await tables(migrated)
    await downgrade(migrated)
    assert await tables(migrated) <= {"alembic_version"}
    await upgrade(migrated)
    assert "organizations" in await tables(migrated)


async def seed_two_orgs(url: str) -> None:
    owner = create_async_engine(url)
    async with owner.begin() as conn:
        await conn.execute(text("TRUNCATE organizations, users CASCADE"))
        await conn.execute(text("INSERT INTO users (id, email, name) VALUES ('usr_1', 'a@example.com', 'A')"))
        for org in ("org_a", "org_b"):
            await conn.execute(
                text("INSERT INTO organizations (id, name, slug) VALUES (:o, :o, :o)"), {"o": org}
            )
            await conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, slug) VALUES (:w, :o, 'Production', 'production')"
                ),
                {"w": f"ws_{org}", "o": org},
            )
            await conn.execute(
                text(
                    "INSERT INTO memberships (id, organization_id, user_id, role_key) VALUES (:m, :o, 'usr_1', 'viewer')"
                ),
                {"m": f"mem_{org}", "o": org},
            )
            await conn.execute(
                text(
                    "INSERT INTO invitations (id, organization_id, email, role_key, token_hash, expires_at, invited_by) "
                    "VALUES (:i, :o, 'x@example.com', 'viewer', :t, now() + interval '7 days', 'usr_1')"
                ),
                {"i": f"inv_{org}", "o": org, "t": f"hash_{org}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_logs (organization_id, actor_type, action, prev_hash, hash) "
                    "VALUES (:o, 'system', 'test', '', :h)"
                ),
                {"o": org, "h": f"h_{org}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO secrets (id, organization_id, kind, ciphertext, wrapped_dek, kek_id) "
                    "VALUES (:s, :o, 'test', 'x', 'y', 'k')"
                ),
                {"s": f"sec_{org}", "o": org},
            )
    await owner.dispose()


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_app_role_sees_only_its_organization(migrated, table):
    await seed_two_orgs(migrated)
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', 'org_a', true)"))
        orgs = {r[0] for r in await conn.execute(text(f"SELECT organization_id FROM {table}"))}
    await engine.dispose()
    assert orgs == {"org_a"}


@pytest.mark.parametrize("table", ["workspaces", "memberships", "invitations", "secrets"])
async def test_app_role_cannot_change_other_organization(migrated, table):
    await seed_two_orgs(migrated)
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', 'org_a', true)"))
        updated = await conn.execute(
            text(f"UPDATE {table} SET organization_id = organization_id WHERE organization_id = 'org_b'")
        )
        deleted = await conn.execute(text(f"DELETE FROM {table} WHERE organization_id = 'org_b'"))
    await engine.dispose()
    assert updated.rowcount == 0
    assert deleted.rowcount == 0


async def test_no_organization_context_sees_nothing(migrated):
    await seed_two_orgs(migrated)
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        count = await conn.scalar(text("SELECT count(*) FROM workspaces"))
    await engine.dispose()
    assert count == 0


async def test_organizations_table_shows_only_current(migrated):
    await seed_two_orgs(migrated)
    engine = app_engine(migrated)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', 'org_b', true)"))
        ids = {r[0] for r in await conn.execute(text("SELECT id FROM organizations"))}
    await engine.dispose()
    assert ids == {"org_b"}


async def test_app_role_cannot_insert_into_another_organization(migrated):
    await seed_two_orgs(migrated)
    engine = app_engine(migrated)
    with pytest.raises(Exception, match="row-level security"):
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('nexora.org_id', 'org_a', true)"))
            await conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, slug) VALUES ('ws_x', 'org_b', 'X', 'x')"
                )
            )
    await engine.dispose()


async def test_app_role_does_not_own_tables(migrated):
    engine = create_async_engine(migrated)
    async with engine.connect() as conn:
        owners = {
            r[0]
            for r in await conn.execute(text("SELECT tableowner FROM pg_tables WHERE schemaname = 'public'"))
        }
    await engine.dispose()
    assert APP_ROLE not in owners
