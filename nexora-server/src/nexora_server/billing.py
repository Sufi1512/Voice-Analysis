"""Metered billing: report each organization's audio seconds to Stripe, hour by hour (E9).

Every closed hour (plus a short grace period) becomes one Stripe **billing meter event**
(``POST /v1/billing/meter_events``) for the organization's ``stripe_customer_id``:

- Audio is counted when a session **ends** (its seconds are only final then), so a call
  spanning several hours is billed in the hour it ends and is never missed or split.
- Values are whole seconds. Rounding is carried over: the seconds reported so far always
  equal the recorded seconds so far, rounded, so the invoice matches recorded audio to the
  second however many hours it spans.
- Each hour is written to ``usage_reports`` first (unique per organization and hour), then
  sent with a unique ``identifier`` and the same ``Idempotency-Key``, so neither several
  server replicas nor retries can bill an hour twice. Failed hours are retried next run.

Hours with no audio are recorded but not sent. Stripe's meter should aggregate with
``sum``; a price "per minute" uses ``transform_quantity[divide_by]=60``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexora_server.db import Database, Organization, SessionRecord, UsageReport, utcnow

log = logging.getLogger("nexora.billing")
HOUR = timedelta(hours=1)


class MeterClient(Protocol):
    def send(self, *, customer: str, value: int, at: datetime, identifier: str) -> None: ...


class StripeMeter:
    """Sends Stripe billing meter events with httpx (no Stripe SDK needed)."""

    def __init__(
        self,
        api_key: str,
        event_name: str = "nexora_audio_seconds",
        base_url: str = "https://api.stripe.com",
        http: Any = None,
    ) -> None:
        import httpx

        self.event_name = event_name
        self.http = http or httpx.Client(base_url=base_url, timeout=15.0)
        self._auth = {"Authorization": f"Bearer {api_key}"}

    def send(self, *, customer: str, value: int, at: datetime, identifier: str) -> None:
        r = self.http.post(
            "/v1/billing/meter_events",
            data={
                "event_name": self.event_name,
                "identifier": identifier,
                "timestamp": str(int(at.timestamp())),
                "payload[stripe_customer_id]": customer,
                "payload[value]": str(value),
            },
            headers={**self._auth, "Idempotency-Key": identifier},
        )
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise BillingError(f"stripe {r.status_code}: {msg}"[:480])


class BillingError(Exception):
    pass


@dataclass
class RunResult:
    sent: int = 0
    failed: int = 0
    empty: int = 0


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def recorded_seconds(db: Session, org_id: str, before: datetime) -> float:
    """Audio seconds of the organization's sessions that ended before ``before``."""
    total = db.scalar(
        select(func.coalesce(func.sum(SessionRecord.audio_seconds), 0.0)).where(
            SessionRecord.org_id == org_id,
            SessionRecord.ended_at.is_not(None),
            SessionRecord.ended_at < before,
        )
    )
    return float(total or 0.0)


def _reported_total(db: Session, org_id: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(UsageReport.reported_seconds), 0)).where(
                UsageReport.org_id == org_id
            )
        )
        or 0
    )


def report_usage(
    database: Database,
    meter: MeterClient,
    now: datetime | None = None,
    grace: timedelta = timedelta(minutes=5),
    max_hours: int = 24 * 7,
) -> RunResult:
    """Report every closed hour not yet reported, for each organization with a Stripe
    customer, and retry failed ones. Safe to run on several replicas at once."""
    now = (now or utcnow()).astimezone(UTC)
    last_closed = _hour(now - grace)  # hours ending at or before this are closed
    result = RunResult()
    with database.session() as db:
        orgs = list(
            db.scalars(select(Organization).where(Organization.stripe_customer_id.is_not(None)))
        )
    for org in orgs:
        _report_org(
            database, meter, org.id, str(org.stripe_customer_id), last_closed, max_hours, result
        )
    return result


def _report_org(
    database: Database,
    meter: MeterClient,
    org_id: str,
    customer: str,
    last_closed: datetime,
    max_hours: int,
    result: RunResult,
) -> None:
    with database.session() as db:
        latest = db.scalar(
            select(func.max(UsageReport.period_end)).where(UsageReport.org_id == org_id)
        )
        created = db.scalar(select(Organization.created_at).where(Organization.id == org_id))
    start = _aware(latest) if latest else _hour(_aware(created or utcnow()))
    hours = 0
    while start + HOUR <= last_closed and hours < max_hours:
        end = start + HOUR
        _claim_hour(database, org_id, start, end, result)
        start, hours = end, hours + 1
    # send what is pending or failed (ours or another replica's leftovers), oldest first
    with database.session() as db:
        todo = list(
            db.scalars(
                select(UsageReport)
                .where(UsageReport.org_id == org_id, UsageReport.status.in_(("pending", "failed")))
                .order_by(UsageReport.period_start)
            )
        )
    for rep in todo:
        try:
            meter.send(
                customer=customer,
                value=rep.reported_seconds,
                at=_aware(rep.period_end) - timedelta(seconds=1),
                identifier=rep.identifier,
            )
        except Exception as exc:
            result.failed += 1
            log.warning("billing report failed", extra={"org_id": org_id, "error": str(exc)})
            with database.session() as db:
                r = db.get(UsageReport, rep.id)
                if r is not None:
                    r.status, r.error = "failed", str(exc)[:500]
            continue
        result.sent += 1
        with database.session() as db:
            r = db.get(UsageReport, rep.id)
            if r is not None:
                r.status, r.error, r.sent_at = "sent", None, utcnow()


def _claim_hour(
    database: Database, org_id: str, start: datetime, end: datetime, result: RunResult
) -> None:
    """Write the hour's report row (unique per org and hour). Another replica that got
    there first wins; then this does nothing."""
    try:
        with database.session() as db:
            recorded = recorded_seconds(db, org_id, end)
            in_hour = recorded - recorded_seconds(db, org_id, start)
            value = round(recorded) - _reported_total(db, org_id)  # carry the rounding
            ident = f"nexora-{org_id}-{start.strftime('%Y%m%dT%H')}"
            db.add(
                UsageReport(
                    org_id=org_id,
                    period_start=start,
                    period_end=end,
                    audio_seconds=round(in_hour, 3),
                    reported_seconds=max(value, 0),
                    identifier=ident,
                    status="pending" if value > 0 else "empty",
                )
            )
            if value <= 0:
                result.empty += 1
    except IntegrityError:
        pass  # another replica claimed this hour
