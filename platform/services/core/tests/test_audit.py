"""C4: append-only audit log with a per-organization hash chain (AC-7)."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexora_core.audit import record, verify_chain
from tests.db_harness import app_engine


@pytest.fixture
async def org(migrated):
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(text("TRUNCATE organizations CASCADE"))
        for o in ("org_a", "org_b"):
            await conn.execute(
                text("INSERT INTO organizations (id, name, slug) VALUES (:o, :o, :o)"), {"o": o}
            )
    await owner.dispose()
    return "org_a"


async def in_org(url: str, org_id: str, *entries: dict) -> None:
    engine = app_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org_id})
        for entry in entries:
            await record(conn, organization_id=org_id, **entry)
    await engine.dispose()


async def chain_ok(url: str, org_id: str):
    engine = app_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org_id})
        result = await verify_chain(conn, org_id)
    await engine.dispose()
    return result


ENTRY = {
    "actor_type": "user",
    "actor_id": "usr_1",
    "action": "member.invited",
    "target_type": "invitation",
    "target_id": "inv_1",
}


async def test_entries_chain_and_verify(migrated, org):
    await in_org(
        migrated,
        org,
        ENTRY,
        {**ENTRY, "action": "member.role_changed"},
        {**ENTRY, "action": "member.removed"},
    )
    result = await chain_ok(migrated, org)
    assert result.ok
    assert result.entries == 3


async def test_chains_are_per_organization(migrated, org):
    await in_org(migrated, "org_a", ENTRY)
    await in_org(migrated, "org_b", ENTRY)
    assert (await chain_ok(migrated, "org_a")).ok
    assert (await chain_ok(migrated, "org_b")).ok


@pytest.mark.parametrize("statement", ["UPDATE audit_logs SET action = 'x'", "DELETE FROM audit_logs"])
async def test_service_role_cannot_rewrite_history(migrated, org, statement):
    await in_org(migrated, org, ENTRY)
    engine = app_engine(migrated)
    with pytest.raises(Exception, match="permission denied"):
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('nexora.org_id', :o, true)"), {"o": org})
            await conn.execute(text(statement))
    await engine.dispose()


async def test_tampering_is_detected(migrated, org):
    await in_org(
        migrated, org, ENTRY, {**ENTRY, "action": "member.removed"}, {**ENTRY, "action": "org.renamed"}
    )
    owner = create_async_engine(migrated)  # someone with direct database access
    async with owner.begin() as conn:
        second = await conn.scalar(
            text("SELECT id FROM audit_logs WHERE organization_id = :o ORDER BY id OFFSET 1 LIMIT 1"),
            {"o": org},
        )
        await conn.execute(
            text("UPDATE audit_logs SET details = '{\"forged\": true}' WHERE id = :i"), {"i": second}
        )
    await owner.dispose()
    result = await chain_ok(migrated, org)
    assert not result.ok
    assert result.first_bad_id == second


async def test_forged_insert_is_detected(migrated, org):
    await in_org(migrated, org, ENTRY)
    owner = create_async_engine(migrated)
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO audit_logs (organization_id, actor_type, action, prev_hash, hash) "
                "VALUES (:o, 'system', 'fake', 'x', 'y')"
            ),
            {"o": org},
        )
    await owner.dispose()
    assert not (await chain_ok(migrated, org)).ok


async def test_concurrent_writes_keep_one_chain(migrated, org):
    await asyncio.gather(*(in_org(migrated, org, {**ENTRY, "target_id": f"inv_{i}"}) for i in range(12)))
    result = await chain_ok(migrated, org)
    assert result.ok
    assert result.entries == 12


async def test_details_must_not_carry_secrets(migrated, org):
    with pytest.raises(ValueError, match="password"):
        await in_org(migrated, org, {**ENTRY, "details": {"password": "hunter2"}})
