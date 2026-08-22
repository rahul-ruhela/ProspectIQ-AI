"""Aggregates every v1 route into a single router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, agents, analytics, auth, campaigns, companies, crm

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(auth.users_router)
api_router.include_router(campaigns.router)
api_router.include_router(campaigns.jobs_router)
api_router.include_router(companies.router)
api_router.include_router(agents.router)
api_router.include_router(crm.router)
api_router.include_router(analytics.router)
api_router.include_router(admin.router)
api_router.include_router(admin.reference_router)
