"""Authentication routes. Tokens travel in httpOnly cookies; a readable CSRF cookie pairs them."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from twinpm.config import get_settings
from twinpm.core import rate_limit
from twinpm.core.errors import UnauthorizedError
from twinpm.core.rbac import ROLE_PERMISSIONS
from twinpm.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    new_csrf_token,
)
from twinpm.db.models import Organization, Program, User
from twinpm.deps import DB, Ctx
from twinpm.schemas.auth import (
    DemoUser,
    LoginRequest,
    MeResponse,
    OrgOut,
    SessionResponse,
    UserOut,
)
from twinpm.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_PATH = "/api/v1/auth"


def _set_session_cookies(response: Response, access: str, refresh: str) -> str:
    s = get_settings()
    csrf = new_csrf_token()

    def put(name: str, value: str, *, max_age: int, path: str, httponly: bool) -> None:
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            path=path,
            httponly=httponly,
            secure=s.cookie_secure,
            samesite="lax",
        )

    put(ACCESS_COOKIE, access, max_age=s.jwt_access_ttl_seconds, path="/", httponly=True)
    put(
        REFRESH_COOKIE, refresh, max_age=s.jwt_refresh_ttl_seconds, path=REFRESH_PATH, httponly=True
    )
    # Readable by the SPA for the double-submit CSRF header.
    put(CSRF_COOKIE, csrf, max_age=s.jwt_refresh_ttl_seconds, path="/", httponly=False)
    return csrf


async def _session(
    session: DB, issued: auth_service.IssuedTokens, response: Response
) -> SessionResponse:
    org = await session.get(Organization, issued.user.org_id)
    if org is None:
        raise UnauthorizedError("Organisation not found")
    csrf = _set_session_cookies(response, issued.access_token, issued.refresh_token)
    return SessionResponse(
        user=UserOut.model_validate(issued.user), org_slug=org.slug, csrf_token=csrf
    )


@router.post("/login", response_model=SessionResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, session: DB
) -> SessionResponse:
    ip = request.client.host if request.client else "unknown"
    await rate_limit.hit("auth", f"{ip}:{body.email}", get_settings().rate_limit_auth_per_minute)
    issued = await auth_service.login(session, body.email, body.password, body.org_slug)
    return await _session(session, issued, response)


@router.post("/refresh", response_model=SessionResponse)
async def refresh(request: Request, response: Response, session: DB) -> SessionResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise UnauthorizedError("No refresh token")
    ip = request.client.host if request.client else "unknown"
    await rate_limit.hit("refresh", ip, get_settings().rate_limit_auth_per_minute * 6)
    issued = await auth_service.refresh(session, token)
    return await _session(session, issued, response)


@router.post("/logout", status_code=204)
async def logout(request: Request, session: DB) -> Response:
    await auth_service.logout(session, request.cookies.get(REFRESH_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


@router.get("/me", response_model=MeResponse)
async def me(ctx: Ctx, session: DB) -> MeResponse:
    user = await session.get(User, ctx.user_id)
    org = await session.get(Organization, ctx.org_id)
    if user is None or org is None:
        raise UnauthorizedError("Session no longer valid")
    program_id = (
        await session.execute(
            select(Program.id)
            .where(Program.org_id == ctx.org_id, Program.deleted_at.is_(None))
            .order_by(Program.owner_user_id == ctx.user_id, Program.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    return MeResponse(
        user=UserOut.model_validate(user),
        org=OrgOut.model_validate(org),
        person_id=ctx.person_id,
        permissions=sorted(p.value for p in ROLE_PERMISSIONS.get(ctx.role, frozenset())),
        demo_mode=get_settings().effective_demo_mode,
        default_program_id=program_id,
    )


@router.get("/demo-users", response_model=list[DemoUser])
async def demo_users(session: DB) -> list[DemoUser]:
    """Lists the seeded demo users. Empty unless demo mode is active."""
    if not get_settings().effective_demo_mode:
        return []
    rows = (
        await session.execute(
            select(User)
            .join(Organization, Organization.id == User.org_id)
            .where(Organization.slug == "novapay", User.deleted_at.is_(None))
            .order_by(User.role, User.name)
        )
    ).scalars()
    return [DemoUser(email=u.email, name=u.name, role=u.role) for u in rows]
