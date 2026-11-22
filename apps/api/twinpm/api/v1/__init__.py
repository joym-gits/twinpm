"""Version 1 API router aggregation."""

from fastapi import APIRouter

from twinpm.api.v1 import (
    admin,
    auth,
    chat,
    comms,
    delegation,
    events,
    insights,
    org,
    planning,
    program,
    risk,
    strategy,
    tokens,
    twin,
)

api_router = APIRouter()
for module in (
    auth,
    org,
    program,
    planning,
    delegation,
    risk,
    insights,
    twin,
    events,
    chat,
    comms,
    strategy,
    tokens,
    admin,
):
    api_router.include_router(module.router)
