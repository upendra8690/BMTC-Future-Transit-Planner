"""Audit trail for every data change: imports, verification decisions, scenario edits and admin actions."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog, utcnow


def record_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: int | str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    text = json.dumps(detail, default=str, ensure_ascii=False) if detail is not None else None
    session.add(
        AuditLog(
            created_at=utcnow(),
            actor=actor[:100],
            action=action[:100],
            entity=entity[:100],
            entity_id=str(entity_id)[:50] if entity_id is not None else None,
            detail=text[:4000] if text else None,
            ip=(ip or "")[:64] or None,
        )
    )
