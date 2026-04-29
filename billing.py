import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8501")


PLAN_LIMITS = {
    "free": {
        "questions_per_month": 20,
        "files_per_month": 2,
        "manual_records_per_month": 50
    },
    "pro": {
        "questions_per_month": 1000,
        "files_per_month": 100,
        "manual_records_per_month": 5000
    },
    "enterprise": {
        "questions_per_month": 999999,
        "files_per_month": 999999,
        "manual_records_per_month": 999999
    }
}


def get_plan_limits(plan: str):
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def create_checkout_session(email: str, tenant_id: int):
    if not stripe.api_key or not STRIPE_PRO_PRICE_ID:
        return {
            "error": "Stripe is not configured yet. Add STRIPE_SECRET_KEY and STRIPE_PRO_PRICE_ID in .env"
        }

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[
            {
                "price": STRIPE_PRO_PRICE_ID,
                "quantity": 1
            }
        ],
        success_url=f"{APP_URL}?billing=success",
        cancel_url=f"{APP_URL}?billing=cancel",
        metadata={
            "tenant_id": str(tenant_id)
        }
    )

    return {
        "checkout_url": session.url
    }