#!/usr/bin/env python3
"""Import a GTFS ZIP from the command line, with the same checks and audit trail as the admin API.

Run from the project folder, with the same .env the server uses. Examples:

  python scripts/import_gtfs.py --file C:/Downloads/feed.zip --new-source "Publisher name" --kind UNKNOWN
  python scripts/import_gtfs.py --file C:/Downloads/feed.zip --source-id 3
  python scripts/import_gtfs.py --source-id 3 --verify --note "Checked against the publisher's own page"

Official data is never automatic. A source yields OFFICIAL_VERIFIED data only when --verify is given
explicitly, and only for a source created with --kind OFFICIAL. Anyone who can run this script can change
the database, so keep the server folder private.

Exit codes: 0 success, 1 usage or file error, 2 feed rejected, 3 verification refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.gtfs.importer import (  # noqa: E402
    classification_for_source,
    fare_counts,
    import_feed,
    import_summary,
)
from app.models import (  # noqa: E402
    KIND_COMMUNITY,
    KIND_OFFICIAL,
    KIND_SYNTHETIC,
    KIND_UNKNOWN,
    STATUS_COMPLETED,
    DataSource,
)
from app.security import safe_filename  # noqa: E402
from app.services.audit import record_audit  # noqa: E402
from app.services.verification import VerificationError, set_verification  # noqa: E402

KINDS = (KIND_OFFICIAL, KIND_COMMUNITY, KIND_SYNTHETIC, KIND_UNKNOWN)
EXIT_OK, EXIT_USAGE, EXIT_REJECTED, EXIT_REFUSED = 0, 1, 2, 3


class UsageError(Exception):
    """A problem with how the command was run, reported without a traceback."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a GTFS ZIP into the planner database.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=Path, help="GTFS ZIP file to import")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source-id", type=int, help="Use an existing data source")
    target.add_argument("--new-source", metavar="PUBLISHER", help="Create a data source for this publisher")
    parser.add_argument("--name", help="Name for a new data source (default: the file name)")
    parser.add_argument("--kind", choices=KINDS, default=KIND_UNKNOWN, help="Kind for a new data source")
    parser.add_argument("--license", default="Not specified", help="Licence for a new data source")
    parser.add_argument("--source-url", help="Where the feed is published, starting with http:// or https://")
    parser.add_argument("--verify", action="store_true", help="Verify the source after importing (OFFICIAL only)")
    parser.add_argument("--revoke", action="store_true", help="Withdraw verification from the source")
    parser.add_argument("--note", default="", help="Verification note, shown to administrators")
    return parser.parse_args(argv)


def check_arguments(args: argparse.Namespace) -> None:
    if args.verify and args.revoke:
        raise UsageError("use either --verify or --revoke, not both")
    if args.new_source is not None and (args.verify or args.revoke):
        raise UsageError("verify an existing source with --source-id, after it has been created and imported")
    if args.new_source is not None and args.file is None:
        raise UsageError("--new-source needs --file")
    if args.file is None and not (args.verify or args.revoke):
        raise UsageError("nothing to do: give --file to import, or --verify / --revoke for an existing source")
    if args.source_url and not args.source_url.startswith(("http://", "https://")):
        raise UsageError("--source-url must start with http:// or https://")
    if args.source_url and len(args.source_url) > 500:
        raise UsageError("--source-url must be at most 500 characters")
    if len(args.license.strip()) > 200:
        raise UsageError("--license must be at most 200 characters")
    if args.new_source is not None:
        if not 1 <= len(args.new_source.strip()) <= 200:
            raise UsageError("--new-source needs a publisher name of 1 to 200 characters")
        if not 1 <= len((args.name or args.file.name).strip()) <= 200:
            raise UsageError("the data source name must be 1 to 200 characters; pass a shorter --name")


def read_feed(path: Path, limit: int) -> bytes:
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    size = path.stat().st_size
    if size > limit:
        raise UsageError(f"the file is {size:,} bytes, above the limit of {limit:,} (MAX_UPLOAD_MB)")
    return path.read_bytes()


def resolve_source(session, args: argparse.Namespace) -> DataSource:
    if args.source_id is not None:
        source = session.get(DataSource, args.source_id)
        if source is None:
            raise UsageError(f"no data source with id {args.source_id}")
        return source
    source = DataSource(
        name=(args.name or args.file.name).strip(),
        publisher=args.new_source.strip(),
        source_url=args.source_url or None,
        license=args.license.strip(),
        kind=args.kind,
        verified=False,
    )
    session.add(source)
    session.flush()
    record_audit(
        session, actor="cli", action="data_source.create", entity="data_source", entity_id=source.id,
        detail={"name": source.name, "kind": source.kind},
    )
    session.commit()
    return source


def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    feed = read_feed(args.file, settings.max_upload_bytes) if args.file else None

    db = Database(settings.database_url)
    db.create_schema()
    session = db.session()
    try:
        source = resolve_source(session, args)
        if args.verify and source.kind != KIND_OFFICIAL:
            print("verification refused: only sources of kind OFFICIAL can be verified", file=sys.stderr)
            return EXIT_REFUSED

        output: dict = {}
        exit_code = EXIT_OK
        if feed is not None:
            imp = import_feed(
                session, feed, filename=safe_filename(args.file.name), source=source,
                settings=settings, actor="cli",
            )
            fares = fare_counts(session, [imp.id]).get(imp.id, 0)
            output["import"] = import_summary(imp, fares)
            if imp.status != STATUS_COMPLETED:
                exit_code = EXIT_REJECTED
        if args.verify or args.revoke:
            changed = set_verification(session, source, verified=args.verify, note=args.note, actor="cli")
            session.commit()
            output["verification"] = {
                "source_id": source.id,
                "verified": source.verified,
                "reclassified_imports": changed,
                "classification_of_source": classification_for_source(source),
            }
        print(json.dumps(output, indent=2, default=str))
        return exit_code
    finally:
        session.close()
        db.dispose()


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:  # argparse exits with 2 on a bad option; this script reserves 2 for rejected feeds
        return EXIT_OK if exc.code in (0, None) else EXIT_USAGE
    try:
        check_arguments(args)
        return run(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except VerificationError as exc:
        print(f"verification refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
