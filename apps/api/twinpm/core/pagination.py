"""Cursor-based pagination over (created_at, id)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

from pydantic import BaseModel

from twinpm.core.errors import AppError


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(id_)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, id_ = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except (ValueError, TypeError) as exc:
        raise AppError("Invalid cursor") from exc
