"""Administrator decisions about data sources.

Verification is the only route to OFFICIAL_VERIFIED data. The admin API and the command-line importer both
call set_verification, so every decision is recorded the same way: a verification record, the reclassified
imports and an audit entry.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..gtfs.importer import reclassify_source_imports
from ..models import KIND_OFFICIAL, DataSource, VerificationRecord, utcnow
from .audit import record_audit


class VerificationError(ValueError):
    """A decision the rules do not allow, such as verifying a source that is not marked OFFICIAL."""


def set_verification(
    session: Session,
    source: DataSource,
    *,
    verified: bool,
    note: str,
    actor: str,
    ip: str | None = None,
) -> int:
    """Verify or revoke a source and move its stored imports to the matching classification.

    Returns the number of imports whose classification changed. Does not commit; the caller does.
    """
    if verified and source.kind != KIND_OFFICIAL:
        raise VerificationError("Only sources of kind OFFICIAL can be verified.")
    cleaned = note.strip() or None
    if verified and cleaned is None:
        raise VerificationError(
            "Verifying a source needs its evidence: the publisher page, the date checked and the licence."
        )
    source.verified = verified
    source.verification_note = cleaned
    source.verified_by = actor
    source.verified_at = utcnow() if verified else None
    session.add(
        VerificationRecord(
            data_source_id=source.id,
            action="VERIFIED" if verified else "REVOKED",
            note=cleaned,
            actor=actor,
        )
    )
    changed = reclassify_source_imports(session, source)
    record_audit(
        session,
        actor=actor,
        action="data_source.verify",
        entity="data_source",
        entity_id=source.id,
        detail={"verified": verified, "reclassified_imports": changed},
        ip=ip,
    )
    return changed
