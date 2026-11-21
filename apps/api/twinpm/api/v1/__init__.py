"""Version 1 API router aggregation."""

from fastapi import APIRouter

from twinpm.api.v1 import auth, delegation, events, insights, org, planning, program, risk, twin

api_router = APIRouter()
for module in (auth, org, program, planning, delegation, risk, insights, twin, events):
    api_router.include_router(module.router)
