#!/usr/bin/env python3
"""Give an existing account a staff role from the server's own shell, without the shared admin key.

Run from the project folder, with the same .env (DATABASE_URL) the server uses:

  python scripts/create_admin.py someone@example.org            # administrator
  python scripts/create_admin.py someone@example.org --role editor

The person first registers in the app (Account screen); this script only changes the role of that account. The change
signs the account out and is written to the audit log with the actor "cli". Exit codes: 0 done, 1 refused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.models import ROLES  # noqa: E402
from app.services import accounts  # noqa: E402
from app.services.audit import record_audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Give an existing account a role.")
    parser.add_argument("email", help="the email address the account was registered with")
    parser.add_argument("--role", choices=ROLES, default="admin")
    args = parser.parse_args(argv)
    db = Database(Settings.from_env().database_url)
    try:
        with db.session() as session:
            user = accounts.find_by_email(session, args.email)
            if user is None:
                print("No account uses that email address. Register it in the app first.", file=sys.stderr)
                return 1
            try:
                accounts.set_role(session, user.id, args.role)
            except accounts.AccountError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            record_audit(session, actor="cli", action="user.role", entity="user", entity_id=user.id,
                         detail={"role": args.role}, ip=None)
            session.commit()
            print(f"Account {user.id} now has the role {args.role}.")
            return 0
    finally:
        db.dispose()


if __name__ == "__main__":
    sys.exit(main())
