from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    dues,
    health,
    invoices,
    items,
    locations,
    opening,
    parties,
    purchases,
    rates,
    settings,
    stock,
    stock_ops,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(locations.router)
api_router.include_router(settings.router)
api_router.include_router(audit.router)
api_router.include_router(items.router)
api_router.include_router(parties.router)
api_router.include_router(opening.router)
api_router.include_router(stock.router)
api_router.include_router(dues.router)
api_router.include_router(purchases.router)
api_router.include_router(stock_ops.router)
api_router.include_router(rates.router)
api_router.include_router(invoices.router)
