"""Upcoming-transport announcements kept in the database, so administrators can update them without code changes.

The first read seeds an empty table from registry.UPCOMING (the entries checked when this version was written). From
then on the database is the only source. Administrators add entries and change them through /api/admin/upcoming; every
change must give a reason, passes registry.validate_upcoming(), and is kept in the entry's public history with the old
and new value of each field. Nothing here is ever used by the journey planner.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import TransportAnnouncement, TransportAnnouncementChange, utcnow
from . import registry
from .audit import record_audit

FIELDS = ("name", "transport_type", "location", "announcement", "status", "source_kind", "announced_on",
          "expected_start", "opened_on", "sources", "verified_on", "note")
SEED_ACTOR = "system"
SEED_REASON = "First entry, from the sources checked when this version of the app was written."
HISTORY_LIMIT = 20


class AnnouncementError(ValueError):
    """A change an administrator cannot make. ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _values(row: TransportAnnouncement) -> dict[str, Any]:
    values = {field: getattr(row, field) for field in FIELDS if field != "sources"}
    values["sources"] = json.loads(row.sources_json)
    return values


def _apply(row: TransportAnnouncement, values: dict[str, Any]) -> None:
    for field in FIELDS:
        if field not in values:
            continue
        if field == "sources":
            row.sources_json = json.dumps(values["sources"], ensure_ascii=False)
        elif field in ("location", "announcement", "note"):
            setattr(row, field, (values[field] or "").strip())
        elif field == "name":
            row.name = str(values[field]).strip()
        else:
            setattr(row, field, values[field])


def _history(row: TransportAnnouncement) -> list[dict[str, Any]]:
    return [
        {"at": change.changed_at.isoformat(timespec="seconds") + "Z", "actor": change.actor,
         "reason": change.reason, "changes": json.loads(change.changes_json)}
        for change in row.changes[:HISTORY_LIMIT]
    ]


def _public(row: TransportAnnouncement) -> dict[str, Any]:
    values = _values(row)
    return {
        "id": row.key,
        **values,
        "mode": registry.TYPE_MODE.get(row.transport_type, "other"),
        "official_announcement": row.source_kind == registry.SRC_OFFICIAL,
        "in_planner": False,
        "updated_at": row.updated_at.isoformat(timespec="seconds") + "Z",
        "history": _history(row),
    }


def ensure_seeded(db: Session) -> None:
    """Load the checked entries into an empty table, once. Two first requests at the same time are harmless."""
    if db.scalar(select(func.count()).select_from(TransportAnnouncement)):
        return
    for item in registry.UPCOMING:
        row = TransportAnnouncement(key=item["id"], created_at=utcnow(), updated_at=utcnow())
        _apply(row, item)
        row.changes.append(TransportAnnouncementChange(
            changed_at=utcnow(), actor=SEED_ACTOR, reason=SEED_REASON,
            changes_json=json.dumps({"created": True}),
        ))
        db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _rows(db: Session) -> list[TransportAnnouncement]:
    stmt = select(TransportAnnouncement).options(selectinload(TransportAnnouncement.changes))
    return list(db.scalars(stmt.order_by(TransportAnnouncement.id)))


def list_entries(db: Session) -> dict[str, Any]:
    ensure_seeded(db)
    rows = _rows(db)
    return {
        "checked": max((row.verified_on for row in rows), default=None),
        "statuses": list(registry.PROJECT_STATUSES),
        "transport_types": list(registry.TRANSPORT_TYPES),
        "source_kinds": list(registry.ANNOUNCEMENT_SOURCE_KINDS),
        "note": registry.UPCOMING_NOTE,
        "projects": [_public(row) for row in rows],
    }


def _check(key: str, values: dict[str, Any], today: dt.date) -> None:
    try:
        registry.validate_upcoming([{"id": key, **values}], today)
    except registry.RegistryError as exc:
        raise AnnouncementError(str(exc)) from exc


def create(db: Session, key: str, values: dict[str, Any], *, reason: str, actor: str, ip: str | None,
           today: dt.date) -> dict[str, Any]:
    ensure_seeded(db)
    if db.scalar(select(TransportAnnouncement).where(TransportAnnouncement.key == key)) is not None:
        raise AnnouncementError(f"{key}: an entry with this id already exists", status=409)
    full = {field: values.get(field) for field in FIELDS}
    _check(key, full, today)
    row = TransportAnnouncement(key=key, created_at=utcnow(), updated_at=utcnow())
    _apply(row, full)
    row.changes.append(TransportAnnouncementChange(
        changed_at=utcnow(), actor=actor, reason=reason.strip(),
        changes_json=json.dumps({"created": True}),
    ))
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, action="upcoming.create", entity="transport_announcement", entity_id=key,
                 detail={"status": row.status, "source_kind": row.source_kind, "reason": reason.strip()}, ip=ip)
    db.commit()
    return _public(row)


def update(db: Session, key: str, changes: dict[str, Any], *, reason: str, actor: str, ip: str | None,
           today: dt.date) -> dict[str, Any]:
    ensure_seeded(db)
    row = db.scalar(select(TransportAnnouncement).where(TransportAnnouncement.key == key))
    if row is None:
        raise AnnouncementError(f"{key}: no such entry", status=404)
    before = _values(row)
    after = {**before, **{field: value for field, value in changes.items() if field in FIELDS}}
    _check(key, after, today)
    diff = {field: [before[field], after[field]] for field in FIELDS if before[field] != after[field]}
    if not diff:
        raise AnnouncementError(f"{key}: nothing changed")
    _apply(row, after)
    row.updated_at = utcnow()
    row.changes.insert(0, TransportAnnouncementChange(
        changed_at=utcnow(), actor=actor, reason=reason.strip(),
        changes_json=json.dumps(diff, ensure_ascii=False),
    ))
    record_audit(db, actor=actor, action="upcoming.update", entity="transport_announcement", entity_id=key,
                 detail={"fields": sorted(diff), "reason": reason.strip()}, ip=ip)
    db.commit()
    return _public(row)
