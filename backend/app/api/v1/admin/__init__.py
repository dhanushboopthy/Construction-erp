"""The Duolink admin API (Milestone 16, ADR 0012), at admin.<BASE_DOMAIN>/api/v1/admin only."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin_host
from app.api.v1.admin import auth, billing, monitoring, staff, tenants, users

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_host)])
router.include_router(auth.router)
router.include_router(billing.router)
router.include_router(monitoring.router)
router.include_router(staff.router)
router.include_router(tenants.router)
router.include_router(users.router)
