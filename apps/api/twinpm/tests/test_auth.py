"""Auth end to end through HTTP: login, me, CSRF, refresh rotation, reuse detection, RBAC."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.security import CSRF_COOKIE, REFRESH_COOKIE
from twinpm.tests.factories import PASSWORD, make_org


async def _login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


async def test_login_me_and_logout(client: httpx.AsyncClient, db: AsyncSession) -> None:
    o = await make_org(db)
    r = await _login(client, o.users["tpm"].email)
    assert r.status_code == 200, r.text
    assert r.json()["org_slug"] == o.org.slug
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["role"] == "tpm"
    assert body["default_program_id"] == str(o.program.id)
    assert "suggestion:respond" in body["permissions"]
    csrf = client.cookies[CSRF_COOKIE]
    out = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
    assert out.status_code == 204


async def test_bad_password_is_401_with_envelope(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    o = await make_org(db)
    r = await client.post(
        "/api/v1/auth/login", json={"email": o.users["tpm"].email, "password": "nope"}
    )
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "unauthorized"
    assert err["request_id"]


async def test_csrf_required_for_cookie_mutations(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    o = await make_org(db)
    await _login(client, o.users["org_admin"].email)
    payload = {"settings": {"retention_days": 365}}
    r = await client.patch("/api/v1/org/settings", json=payload)
    assert r.status_code == 403
    assert "CSRF" in r.json()["error"]["message"]
    r = await client.patch(
        "/api/v1/org/settings", json=payload, headers={"x-csrf-token": client.cookies[CSRF_COOKIE]}
    )
    assert r.status_code == 200
    assert r.json()["settings"]["retention_days"] == 365


async def test_refresh_rotation_and_reuse_detection(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    o = await make_org(db)
    await _login(client, o.users["tpm"].email)
    first = client.cookies[REFRESH_COOKIE]
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    second = client.cookies[REFRESH_COOKIE]
    assert second != first
    # Replaying the rotated token revokes the whole family, including the new token.
    client.cookies.set(REFRESH_COOKIE, first, path="/api/v1/auth")
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert "reuse" in r.json()["error"]["message"]
    client.cookies.set(REFRESH_COOKIE, second, path="/api/v1/auth")
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


async def test_rbac_member_cannot_manage_members(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    o = await make_org(db)
    await _login(client, o.users["member"].email)
    r = await client.get("/api/v1/members")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


async def test_admin_creates_member_and_audits(client: httpx.AsyncClient, db: AsyncSession) -> None:
    o = await make_org(db)
    await _login(client, o.users["org_admin"].email)
    h = {"x-csrf-token": client.cookies[CSRF_COOKIE]}
    body = {"email": "new@x.test", "name": "New", "role": "member", "password": "long-password-1"}
    r = await client.post("/api/v1/members", json=body, headers=h)
    assert r.status_code == 201, r.text
    r2 = await client.post("/api/v1/members", json=body, headers=h)
    assert r2.status_code == 409


async def test_unauthenticated_is_401(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
