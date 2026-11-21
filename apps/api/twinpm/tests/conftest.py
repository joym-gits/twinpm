"""Test infrastructure: Postgres (pgvector) and Redis via testcontainers.

Set TEST_DATABASE_URL / TEST_REDIS_URL to reuse running services instead (faster locally).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

_containers: list[object] = []


def _boot_services() -> None:
    db_url = os.environ.get("TEST_DATABASE_URL")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not db_url:
        from testcontainers.postgres import PostgresContainer

        pg = PostgresContainer("pgvector/pgvector:pg16", username="t", password="t", dbname="t")
        pg.start()
        _containers.append(pg)
        db_url = (
            f"postgresql+asyncpg://t:t@{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/t"
        )
    if not redis_url:
        from testcontainers.redis import RedisContainer

        rc = RedisContainer("redis:7-alpine")
        rc.start()
        _containers.append(rc)
        redis_url = f"redis://{rc.get_container_host_ip()}:{rc.get_exposed_port(6379)}/0"
    os.environ.update(
        DATABASE_URL=db_url,
        REDIS_URL=redis_url,
        ENV="test",
        DEMO_MODE="true",
        ANTHROPIC_API_KEY="",
        LOG_JSON="false",
        LOG_LEVEL="WARNING",
        MODELS_DIR=os.environ.get("TEST_MODELS_DIR", str(Path(__file__).parent / ".models")),
        FERNET_KEY="8Tb2t8Qd5Q3Hb3n5mTqg9Zg6n8wW1v1J2XoUeYvVZ0s=",
    )


def pytest_configure(config: pytest.Config) -> None:
    _boot_services()
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


def pytest_unconfigure(config: pytest.Config) -> None:
    for c in _containers:
        c.stop()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def app() -> Iterator[object]:
    from twinpm.main import app as fastapi_app

    yield fastapi_app


@pytest.fixture
async def db() -> AsyncIterator[object]:
    from twinpm.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(app: object) -> AsyncIterator[object]:
    import httpx

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def unique() -> str:
    return uuid.uuid4().hex[:8]
