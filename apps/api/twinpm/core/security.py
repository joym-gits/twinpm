"""Password hashing (Argon2), JWT access tokens, opaque refresh/API tokens, CSRF tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from twinpm.config import get_settings
from twinpm.core.errors import UnauthorizedError

_hasher = PasswordHasher()
ALGORITHM = "HS256"
ACCESS_COOKIE = "twinpm_access"
REFRESH_COOKIE = "twinpm_refresh"
CSRF_COOKIE = "twinpm_csrf"
CSRF_HEADER = "x-csrf-token"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=s.jwt_access_ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    try:
        data = jwt.decode(
            token, get_settings().jwt_secret.get_secret_value(), algorithms=[ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    if data.get("typ") != "access":
        raise UnauthorizedError("Invalid token type")
    return AccessClaims(uuid.UUID(data["sub"]), uuid.UUID(data["org"]), str(data["role"]))


def new_opaque_token(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)
