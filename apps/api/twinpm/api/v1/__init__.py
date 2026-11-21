"""Version 1 API router aggregation."""

from fastapi import APIRouter

from twinpm.api.v1 import auth, org

api_router = APIRouter()
for module in (auth, org):
    api_router.include_router(module.router)
