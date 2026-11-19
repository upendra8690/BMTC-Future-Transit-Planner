"""Service notices: short, dated notices that an administrator copies from an official source.

The app has no authorised live alerts feed, so it never shows an alert of its own making. An administrator may post a
notice only if it links to an official source: a government website, BMRCL's website, or the official X accounts of
BMTC and BMRCL. Every notice ends within 31 days and is hidden after its end date. Each create, change or withdrawal
needs a reason and is written to the audit log.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NOTICE_KINDS, NOTICE_MODES, ServiceNotice, utcnow
from .audit import record_audit

MAX_DAYS = 31
MAX_START_AHEAD_DAYS = 60
ADMIN_HISTORY_DAYS = 90
# Websites accepted as official sources: any government site, and BMRCL's own domain.
OFFICIAL_DOMAINS = ("gov.in", "nic.in", "bmrc.co.in")
# Official X (Twitter) accounts accepted as sources. Extend only with accounts the operator itself runs.
OFFICIAL_X_ACCOUNTS = ("bmtc_bengaluru", "officialbmrcl")
FIELDS = ("title", "body", "kind", "mode", "source_title", "source_url", "starts_on", "ends_on", "withdrawn")
KIND_ORDER = {kind: i for i, kind in enumerate(NOTICE_KINDS)}


class NoticeError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def is_official_source(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS):
        return True
    if host in ("x.com", "www.x.com", "twitter.com", "www.twitter.com"):
        account = parts.path.strip("/").split("/")[0].lower()
        return account in OFFICIAL_X_ACCOUNTS
    return False


def _status(row: ServiceNotice, today: dt.date) -> str:
    if row.withdrawn:
        return "WITHDRAWN"
    if row.ends_on < today:
        return "ENDED"
    if row.starts_on > today:
        return "SCHEDULED"
    return "ACTIVE"


def _public(row: ServiceNotice, today: dt.date) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "kind": row.kind,
        "mode": row.mode,
        "source": {"title": row.source_title, "url": row.source_url},
        "starts_on": row.starts_on.isoformat(),
        "ends_on": row.ends_on.isoformat(),
        "status": _status(row, today),
        "written_by_app_administrator": True,
        "updated_at": row.updated_at.isoformat(timespec="seconds") + "Z",
    }


def _check(values: dict[str, Any], today: dt.date, *, creating: bool) -> None:
    if values["kind"] not in NOTICE_KINDS:
        raise NoticeError(f"kind must be one of {', '.join(NOTICE_KINDS)}")
    if values["mode"] not in NOTICE_MODES:
        raise NoticeError(f"mode must be one of {', '.join(NOTICE_MODES)}")
    if not is_official_source(values["source_url"]):
        raise NoticeError("source_url must be an https link to an official source: a gov.in or nic.in site, "
                          "bmrc.co.in, or the official BMTC or BMRCL account on X")
    starts, ends = values["starts_on"], values["ends_on"]
    if ends < starts:
        raise NoticeError("ends_on cannot be before starts_on")
    if (ends - starts).days > MAX_DAYS:
        raise NoticeError(f"a notice can run for at most {MAX_DAYS} days; longer plans belong in Upcoming transport")
    if creating and ends < today:
        raise NoticeError("ends_on is already past")
    if creating and (starts - today).days > MAX_START_AHEAD_DAYS:
        raise NoticeError(f"starts_on can be at most {MAX_START_AHEAD_DAYS} days ahead")


def list_active(db: Session, today: dt.date) -> dict[str, Any]:
    rows = db.scalars(select(ServiceNotice).where(
        ServiceNotice.withdrawn.is_(False), ServiceNotice.starts_on <= today, ServiceNotice.ends_on >= today))
    notices = sorted((_public(row, today) for row in rows), key=lambda n: (KIND_ORDER[n["kind"]], n["ends_on"]))
    return {"today": today.isoformat(), "live_alerts_feed": False, "notices": notices}


def list_for_admin(db: Session, today: dt.date) -> dict[str, Any]:
    since = today - dt.timedelta(days=ADMIN_HISTORY_DAYS)
    rows = db.scalars(select(ServiceNotice).where(ServiceNotice.ends_on >= since).order_by(ServiceNotice.id.desc()))
    return {"today": today.isoformat(), "kinds": list(NOTICE_KINDS), "modes": list(NOTICE_MODES),
            "max_days": MAX_DAYS, "notices": [_public(row, today) for row in rows]}


def create(db: Session, values: dict[str, Any], *, reason: str, actor: str, ip: str | None,
           today: dt.date) -> dict[str, Any]:
    full = {field: values.get(field) for field in FIELDS}
    full["withdrawn"] = False
    _check(full, today, creating=True)
    row = ServiceNotice(created_by=actor, created_at=utcnow(), updated_at=utcnow(),
                        **{field: full[field] for field in FIELDS})
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, action="notice.create", entity="service_notice", entity_id=str(row.id),
                 detail={"kind": row.kind, "source_url": row.source_url, "ends_on": row.ends_on.isoformat(),
                         "reason": reason.strip()}, ip=ip)
    db.commit()
    return _public(row, today)


def update(db: Session, notice_id: int, changes: dict[str, Any], *, reason: str, actor: str, ip: str | None,
           today: dt.date) -> dict[str, Any]:
    row = db.get(ServiceNotice, notice_id)
    if row is None:
        raise NoticeError(f"{notice_id}: no such notice", status=404)
    before = {field: getattr(row, field) for field in FIELDS}
    after = {**before, **{field: value for field, value in changes.items() if field in FIELDS}}
    _check(after, today, creating=False)
    diff = {field: [_plain(before[field]), _plain(after[field])] for field in FIELDS if before[field] != after[field]}
    if not diff:
        raise NoticeError(f"{notice_id}: nothing changed")
    for field in diff:
        setattr(row, field, after[field])
    row.updated_at = utcnow()
    action = "notice.withdraw" if diff.get("withdrawn") == [False, True] else "notice.update"
    record_audit(db, actor=actor, action=action, entity="service_notice", entity_id=str(row.id),
                 detail={"fields": sorted(diff), "reason": reason.strip()}, ip=ip)
    db.commit()
    return _public(row, today)


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, dt.date) else value
