"""Plan & billing: a company owner renews Duolink online with Razorpay (Milestone 30).

Owner only, and open while the company is read-only (see `services/subscription_access.py`),
so an expired company can pay and be writable again at once. Off unless the Razorpay keys are
set: then GET answers `online_renewal: false` and the writes answer 409 ONLINE_RENEWAL_OFF. The
webhook is the one open route: Razorpay signs its body instead of signing in.
"""

from fastapi import APIRouter, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentTenant, DbSession, OwnerOnly
from app.schemas.online_renewal import (
    RenewalOrderCreate,
    RenewalOrderOut,
    RenewalOverview,
    RenewalResult,
    VerifyRequest,
    WebhookAnswer,
)
from app.services import online_renewal as service
from app.services.platform import razorpay_webhook

router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.get("", response_model=RenewalOverview)
def overview(_: OwnerOnly, tenant: CurrentTenant, db: DbSession) -> RenewalOverview:
    """The plan, when it ends, and the Duolink prices that can be paid online now, each with
    the date the plan would then run to."""
    return service.overview(db, tenant)


@router.post("/orders", response_model=RenewalOrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: RenewalOrderCreate, principal: OwnerOnly, tenant: CurrentTenant, db: DbSession
) -> RenewalOrderOut:
    """A Razorpay order for one price. The amount is the plan's price on the server. 404
    PRICE_NOT_FOUND; 409 PRICE_NOT_OFFERED or ONLINE_RENEWAL_OFF; 502 RAZORPAY_ERROR."""
    return service.create_order(db, tenant, principal.user_id, body)


@router.post("/verify", response_model=RenewalResult)
def verify(
    body: VerifyRequest, _: OwnerOnly, tenant: CurrentTenant, db: DbSession
) -> RenewalResult:
    """Checkout's answer. 400 SIGNATURE_INVALID records nothing; 404 ORDER_NOT_FOUND. The same
    payment twice (or after the webhook) answers 200 with `applied: false`."""
    return service.verify(db, tenant, body)


@router.post("/webhook", response_model=WebhookAnswer)
async def webhook(request: Request, db: DbSession) -> WebhookAnswer:
    """Razorpay's `payment.captured`, signed in `X-Razorpay-Signature` with the webhook secret.
    No sign-in and any address. 400 SIGNATURE_INVALID or BAD_PAYLOAD; 404 while no webhook
    secret is set; 200 for a duplicate or any other event."""
    body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    return await run_in_threadpool(razorpay_webhook.handle, db, body, signature)
