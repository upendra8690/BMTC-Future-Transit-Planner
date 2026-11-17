"""Passenger accounts, sessions, roles, account-saved journeys and notification preferences.

Off unless the server can keep accounts: ACCOUNTS_ENABLED=1 and a PostgreSQL database (DATABASE_URL). On Render's free
disk every account would be erased at the next restart, so the feature refuses to start there. ACCOUNTS_ALLOW_SQLITE=1
exists only for local development and tests.

Security:
- **Passwords.** Stored only as salted scrypt hashes; 10 to 128 characters.
- **Sessions.** A random token is given to the browser once and travels in the "Authorization: Bearer" header, never
  in a cookie, so cross-site requests cannot use it. Only its SHA-256 hash is stored; it expires after 30 days.
- **Lockout.** Eight wrong passwords lock the account for 15 minutes. Sign-in errors never say whether an email
  address exists.
- **Recovery.** No email service is connected, so recovery uses a one-time code shown at registration and stored
  only as a hash. Recovering signs out every session and issues a new code.
- **Roles.** passenger (default), editor (may update upcoming-transport entries) and admin. Only an admin, or the
  ADMIN_API_KEY holder, can change a role.
- **Notifications.** Preferences are stored, but nothing is sent: no delivery service is connected.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from ..database import normalise_url
from ..models import (
    ROLE_PASSENGER,
    ROLES,
    NotificationPreference,
    User,
    UserSavedJourney,
    UserSession,
    utcnow,
)

SESSION_DAYS = 30
MAX_FAILED_LOGINS = 8
LOCK_MINUTES = 15
MIN_PASSWORD, MAX_PASSWORD = 10, 128
MAX_SAVED_JOURNEYS = 50
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}

DISABLED = "ACCOUNTS_DISABLED"
NEEDS_PERSISTENT_DATABASE = "NEEDS_PERSISTENT_DATABASE"


class AccountError(ValueError):
    """A request the account service refuses. ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- availability

def availability(enabled: bool, allow_sqlite: bool, database_url: str) -> str | None:
    """None when accounts may run; otherwise the reason code they are off."""
    if not enabled:
        return DISABLED
    backend = make_url(normalise_url(database_url)).get_backend_name()
    if backend == "postgresql" or (backend == "sqlite" and allow_sqlite):
        return None
    return NEEDS_PERSISTENT_DATABASE


# ---------------------------------------------------------------- secrets

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                               dklen=len(digest) // 2)
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_recovery_code() -> tuple[str, str]:
    code = "-".join(secrets.token_hex(3) for _ in range(4))
    return code, _token_hash(code)


def _check_password(password: str) -> None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise AccountError(f"Use a password of {MIN_PASSWORD} to {MAX_PASSWORD} characters.", 422)


def _normal_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise AccountError("Enter a valid email address.", 422)
    return email


# ---------------------------------------------------------------- accounts and sessions

def public_user(user: User) -> dict[str, Any]:
    return {"id": user.id, "email": user.email, "role": user.role,
            "created_at": user.created_at.isoformat(timespec="seconds") + "Z"}


def register(db: Session, email: str, password: str) -> tuple[User, str]:
    email = _normal_email(email)
    _check_password(password)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AccountError("An account with this email address already exists.", 409)
    code, code_hash = _new_recovery_code()
    user = User(email=email, password_hash=hash_password(password), role=ROLE_PASSENGER, recovery_hash=code_hash,
                failed_logins=0, created_at=utcnow())
    db.add(user)
    db.flush()
    db.add(NotificationPreference(user_id=user.id, service_notices=False, upcoming_changes=False,
                                  updated_at=utcnow()))
    db.commit()
    return user, code


def _start_session(db: Session, user: User, now: dt.datetime) -> tuple[str, dt.datetime]:
    token = secrets.token_urlsafe(32)
    expires = now + dt.timedelta(days=SESSION_DAYS)
    db.add(UserSession(user_id=user.id, token_hash=_token_hash(token), created_at=now, expires_at=expires))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now))
    db.commit()
    return token, expires


def sign_in(db: Session, email: str, password: str, now: dt.datetime | None = None) -> tuple[User, str, dt.datetime]:
    now = now or utcnow()
    wrong = AccountError("Email address or password is incorrect.", 401)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        hash_password(password)  # same work as a real check, so timing does not reveal unknown addresses
        raise wrong
    if user.locked_until is not None and user.locked_until > now:
        raise AccountError("Too many wrong passwords. Try again in a few minutes.", 429)
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins = 0
            user.locked_until = now + dt.timedelta(minutes=LOCK_MINUTES)
        db.commit()
        raise wrong
    user.failed_logins = 0
    user.locked_until = None
    token, expires = _start_session(db, user, now)
    return user, token, expires


def user_for_token(db: Session, token: str, now: dt.datetime | None = None) -> User | None:
    if not token:
        return None
    row = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if row is None or row.expires_at <= (now or utcnow()):
        return None
    return db.get(User, row.user_id)


def sign_out(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AccountError("The current password is incorrect.", 401)
    _check_password(new)
    user.password_hash = hash_password(new)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()


def recover(db: Session, email: str, code: str, new_password: str) -> str:
    """Set a new password with the one-time recovery code. Signs out everywhere and returns a new code."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.recovery_hash or not hmac.compare_digest(_token_hash(code.strip()), user.recovery_hash):
        raise AccountError("The email address or recovery code is incorrect.", 401)
    _check_password(new_password)
    new_code, new_hash = _new_recovery_code()
    user.password_hash = hash_password(new_password)
    user.recovery_hash = new_hash
    user.failed_logins = 0
    user.locked_until = None
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return new_code


def delete_account(db: Session, user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise AccountError("The password is incorrect.", 401)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(UserSavedJourney).where(UserSavedJourney.user_id == user.id))
    db.execute(delete(NotificationPreference).where(NotificationPreference.user_id == user.id))
    db.delete(user)
    db.commit()


def set_role(db: Session, user_id: int, role: str) -> User:
    if role not in ROLES:
        raise AccountError("Unknown role.", 422)
    user = db.get(User, user_id)
    if user is None:
        raise AccountError("No such account.", 404)
    user.role = role
    db.commit()
    return user


# ---------------------------------------------------------------- saved journeys, preferences, export

def journey_out(row: UserSavedJourney) -> dict[str, Any]:
    return {"id": row.id, "origin": row.origin, "destination": row.destination, "modes": row.modes,
            "classification": row.classification, "label": row.label,
            "created_at": row.created_at.isoformat(timespec="seconds") + "Z"}


def journeys(db: Session, user: User) -> list[dict[str, Any]]:
    rows = db.scalars(select(UserSavedJourney).where(UserSavedJourney.user_id == user.id)
                      .order_by(UserSavedJourney.id))
    return [journey_out(row) for row in rows]


def add_journey(db: Session, user: User, values: dict[str, Any]) -> dict[str, Any]:
    if len(journeys(db, user)) >= MAX_SAVED_JOURNEYS:
        raise AccountError(f"An account can keep up to {MAX_SAVED_JOURNEYS} journeys.", 409)
    row = UserSavedJourney(user_id=user.id, created_at=utcnow(), **values)
    db.add(row)
    db.commit()
    return journey_out(row)


def remove_journey(db: Session, user: User, journey_id: int) -> None:
    row = db.get(UserSavedJourney, journey_id)
    if row is None or row.user_id != user.id:  # another account's journey is reported as missing
        raise AccountError("No such saved journey.", 404)
    db.delete(row)
    db.commit()


def preferences(db: Session, user: User) -> dict[str, Any]:
    row = db.get(NotificationPreference, user.id)
    return {"service_notices": bool(row and row.service_notices),
            "upcoming_changes": bool(row and row.upcoming_changes), "delivery": "NOT_AVAILABLE"}


def set_preferences(db: Session, user: User, values: dict[str, bool]) -> dict[str, Any]:
    row = db.get(NotificationPreference, user.id) or NotificationPreference(user_id=user.id)
    row.service_notices = bool(values.get("service_notices", False))
    row.upcoming_changes = bool(values.get("upcoming_changes", False))
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    return preferences(db, user)


def export(db: Session, user: User) -> dict[str, Any]:
    """Everything the service keeps about an account. Password and recovery hashes are never included."""
    return {"account": public_user(user), "saved_journeys": journeys(db, user),
            "notification_preferences": preferences(db, user)}
