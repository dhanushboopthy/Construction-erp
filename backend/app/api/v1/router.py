from fastapi import APIRouter

from app.api.v1 import audit, auth, health, items, locations, parties, settings, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(locations.router)
api_router.include_router(settings.router)
api_router.include_router(audit.router)
api_router.include_router(items.router)
api_router.include_router(parties.router)
