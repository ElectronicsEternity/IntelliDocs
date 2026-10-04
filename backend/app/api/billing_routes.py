"""Authenticated checkout/portal endpoints and Stripe-signed notifications."""

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.billing import BillingService

router = APIRouter(prefix="/billing", tags=["billing"])


def get_billing_service():
    return BillingService()


@router.get("/status")
def billing_status(user: AuthenticatedUser = Depends(get_current_user), service=Depends(get_billing_service)):
    return service.status(user.id)


@router.post("/checkout")
def checkout(user: AuthenticatedUser = Depends(get_current_user), service=Depends(get_billing_service)):
    # The frontend cannot submit a customer ID, price or arbitrary return URL.
    return service.checkout(user.id)


@router.post("/portal")
def portal(user: AuthenticatedUser = Depends(get_current_user), service=Depends(get_billing_service)):
    return service.portal(user.id)


@router.post('/checkout/fpx')
def fpx_checkout(user: AuthenticatedUser = Depends(get_current_user), service=Depends(get_billing_service)):
    # Like card checkout, all prices and ownership come from server configuration.
    return service.checkout(user.id, payment_method='fpx')


@router.post("/webhook")
async def webhook(request: Request, service=Depends(get_billing_service)):
    # Stripe has no application login: its signature is the authentication.
    # Bound memory use while preserving exactly the raw bytes Stripe signed.
    payload = bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload) > 1_000_000:
            raise HTTPException(413, "Stripe notification is too large.")
    await run_in_threadpool(service.webhook, bytes(payload), request.headers.get("stripe-signature", ""))
    return {"received": True}
