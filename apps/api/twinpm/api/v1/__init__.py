"""Version 1 API router aggregation."""

from fastapi import APIRouter

from twinpm.api.v1 import (
    admin,
    auth,
    catalog,
    chat,
    comms,
    delegation,
    events,
    insights,
    integrations,
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
    catalog,
    integrations,
):
    api_router.include_router(module.router)
