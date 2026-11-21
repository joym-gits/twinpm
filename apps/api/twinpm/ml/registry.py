"""Versioned filesystem model registry: models/{name}/{version}/model.joblib + metadata.json."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from twinpm.config import get_settings

REQUIRED_MODELS = ("delay_risk", "effort")


@dataclass(frozen=True)
class ModelInfo:
    name: str
    version: str
    path: Path
    metadata: dict[str, Any]


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[tuple[str, str], Any] = {}

    @classmethod
    def default(cls) -> ModelRegistry:
        global _default
        root = Path(get_settings().models_dir).resolve()
        if _default is None or _default.root != root:
            _default = cls(root)
        return _default

    @staticmethod
    def data_hash(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()[:16]

    def save(self, name: str, model: Any, metadata: dict[str, Any]) -> ModelInfo:
        existing = self.versions(name)
        version = f"v{len(existing) + 1:04d}"
        path = self.root / name / version
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path / "model.joblib")
        meta = {
            **metadata,
            "name": name,
            "version": version,
            "trained_at": datetime.now(UTC).isoformat(),
        }
        (path / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))
        (self.root / name / "LATEST").write_text(version)
        return ModelInfo(name, version, path, meta)

    def versions(self, name: str) -> list[str]:
        d = self.root / name
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("v"))

    def latest(self, name: str) -> ModelInfo | None:
        marker = self.root / name / "LATEST"
        if not marker.exists():
            return None
        version = marker.read_text().strip()
        path = self.root / name / version
        meta = json.loads((path / "metadata.json").read_text())
        return ModelInfo(name, version, path, meta)

    def load(self, name: str) -> tuple[Any, ModelInfo] | None:
        info = self.latest(name)
        if info is None:
            return None
        key = (name, info.version)
        if key not in self._cache:
            self._cache[key] = joblib.load(info.path / "model.joblib")
        return self._cache[key], info

    def is_ready(self) -> bool:
        return all(self.latest(n) is not None for n in REQUIRED_MODELS)


_default: ModelRegistry | None = None
