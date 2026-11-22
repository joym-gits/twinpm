"""Fernet encryption for integration secrets at rest."""

from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from twinpm.config import get_settings
from twinpm.core.errors import AppError

SECRET_KEYS = ("token", "api_token", "api_key", "password", "client_secret", "bot_token")


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if key is None or not key.get_secret_value():
        raise AppError("FERNET_KEY is not configured; cannot store integration secrets")
    return Fernet(key.get_secret_value().encode())


def encrypt_config(config: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in config.items():
        out[k] = (
            {"enc": _fernet().encrypt(str(v).encode()).decode()} if (k in SECRET_KEYS and v) else v
        )
    return out


def decrypt_config(config: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in config.items():
        if isinstance(v, dict) and "enc" in v:
            try:
                out[k] = _fernet().decrypt(v["enc"].encode()).decode()
            except InvalidToken as exc:
                raise AppError(f"Cannot decrypt {k}; was FERNET_KEY rotated?") from exc
        else:
            out[k] = v
    return out


def redacted(config: dict[str, Any]) -> dict[str, Any]:
    return {k: ("••••" if isinstance(v, dict) and "enc" in v else v) for k, v in config.items()}
