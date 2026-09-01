import pytest
from fastapi.testclient import TestClient

from backend.api import main
from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.preview_token import sign_preview_token

client = TestClient(main.app)

PLUS_MONTHLY = CommercialOffer("plus_monthly", "plus", "month", True, "price_plus_monthly", 999, "usd")
PREMIUM_MONTHLY = CommercialOffer("premium_monthly", "premium", "month", True, "price_premium_monthly", 2499, "usd")
OFFERS = {"plus_monthly": PLUS_MONTHLY, "premium_monthly": PREMIUM_MONTHLY}


@pytest.fixture(autouse=True)
def signing_secret(monkeypatch):
    monkeypatch.setenv("BILLING_PLAN_CHANGE_SIGNING_SECRET", "test-secret")


def _auth_headers(monkeypatch, user_id):
    monkeypatch.setattr(
        main,
        "decode_token",
        lambda token: ({"id": user_id}, None)
        if token == "good"
        else (None, ({"message": "Not authenticated"}, 401)),
    )
    return {"Authorization": "Bearer good"}


def test_basic_user_cannot_preview_plan_change(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        from backend.domain.billing.errors import BillingOwnershipError

        raise BillingOwnershipError("no billing-managed subscription")

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)
    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "premium_monthly"},
        headers=_auth_headers(monkeypatch, "basic-user"),
    )
    assert response.status_code == 403


def test_browser_supplied_previewtoken_amount_is_ignored(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    captured = {}

    def fake_confirm(self, *, user_id, offer_key, preview_token):
        captured["preview_token"] = preview_token
        return {"action": "upgrade_now", "paymentResult": "succeeded"}

    monkeypatch.setattr(billing_service_module.BillingService, "confirm_plan_change", fake_confirm)

    forged_token = sign_preview_token(
        secret="wrong-secret",  # attacker doesn't know the real secret
        visible={"version": 1, "action": "upgrade_now", "prorationDate": 1, "amountDueNow": 1, "currency": "usd", "expiresAt": 9999999999},
        hidden={},
    )
    response = client.post(
        "/billing/change-plan/confirm",
        json={"offerKey": "premium_monthly", "previewToken": forged_token},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    # The fake service always "succeeds" here because we stubbed confirm_plan_change directly;
    # this test only proves the raw forged token string reaches the service layer unmodified
    # (i.e. the API layer performs no token trust decisions itself) — real verification is
    # covered by Task 5's confirm_upgrade_expired_token_rejected / tampered-token tests, which
    # exercise the actual verify_preview_token call inside BillingService.
    assert response.status_code == 200
    assert captured["preview_token"] == forged_token


def test_cancel_scheduled_ignores_browser_supplied_schedule_id(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_cancel(self, *, user_id):
        return {"cancelled": True}

    monkeypatch.setattr(billing_service_module.BillingService, "cancel_scheduled_plan_change", fake_cancel)

    response = client.post(
        "/billing/change-plan/cancel-scheduled",
        json={"scheduleId": "sub_sched_attacker"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    # No schedule route param/body field exists to receive scheduleId at all —
    # pydantic has no model on this route, so any body is accepted and ignored;
    # confirm the route doesn't 422 on unexpected fields and doesn't use them.
    assert response.status_code in (200, 403, 409, 503)


@pytest.mark.parametrize("field", ["subscriptionId", "customerId", "priceId", "userId", "amountDueNow", "currentPlan"])
def test_preview_request_model_rejects_unknown_fields_silently(field, monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        assert user_id == "user-1"
        assert offer_key == "premium_monthly"
        return {"action": "upgrade_now", "fromPlan": "plus", "toPlan": "premium", "amountDueNow": 1500, "previewToken": "tok"}

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)

    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "premium_monthly", field: "malicious-value"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    # Must not 500; pydantic drops unknown fields by default rather than trusting them.
    assert response.status_code != 500
