"""Test infrastructure: Postgres (pgvector) and Redis via testcontainers.

Set TEST_DATABASE_URL / TEST_REDIS_URL to reuse running services instead (faster locally).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
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
        RATE_LIMIT_AUTH_PER_MINUTE="1000",
        MCP_ALLOWED_HOSTS='["test", "localhost:*"]',
        RATE_LIMIT_AI_PER_MINUTE="1000",
    )


def pytest_configure(config: pytest.Config) -> None:
    _boot_services()
    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


def pytest_unconfigure(config: pytest.Config) -> None:
    for c in _containers:
        c.stop()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def app() -> object:
    from twinpm.main import app as fastapi_app

    return fastapi_app


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


DEMO_PASSWORD = "Demo-password-for-tests-1"


@pytest.fixture(scope="session")
async def seeded() -> dict[str, object]:
    """NovaPay seeded, models trained and ML outputs refreshed (once per test session)."""
    from sqlalchemy import select

    from twinpm.db.models import Organization, User
    from twinpm.db.session import get_sessionmaker
    from twinpm.seed.generator import generate
    from twinpm.seed.loader import load
    from twinpm.services.ml_jobs import train_and_refresh

    async with get_sessionmaker()() as s:
        await load(s, generate(42), DEMO_PASSWORD)
        org_id = (
            await s.execute(select(Organization.id).where(Organization.slug == "novapay"))
        ).scalar_one()
        await train_and_refresh(s, org_id)
        users = {
            u.email.split("@")[0]: u.id
            for u in (await s.execute(select(User).where(User.org_id == org_id))).scalars()
        }
    return {"org_id": org_id, "users": users}


@pytest.fixture
async def priya(client: object, seeded: dict[str, object]) -> object:
    """An HTTP client logged in as Priya (TPM) with the CSRF header set."""
    import httpx

    c: httpx.AsyncClient = client  # type: ignore[assignment]
    r = await c.post(
        "/api/v1/auth/login", json={"email": "priya@novapay.example", "password": DEMO_PASSWORD}
    )
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = c.cookies["twinpm_csrf"]
    return c
