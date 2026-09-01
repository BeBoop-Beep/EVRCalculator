from fastapi.testclient import TestClient

from backend.api import main
from backend.domain.billing.errors import (
    BillingOwnershipError,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
)

client = TestClient(main.app)


def _auth_headers(monkeypatch, user_id):
    monkeypatch.setattr(
        main,
        "decode_token",
        lambda token: ({"id": user_id}, None)
        if token == "good"
        else (None, ({"message": "Not authenticated"}, 401)),
    )
    return {"Authorization": "Bearer good"}


def test_preview_anonymous_rejected():
    response = client.post("/billing/change-plan/preview", json={"offerKey": "premium_monthly"})
    assert response.status_code in (401, 403)


def test_confirm_anonymous_rejected():
    response = client.post(
        "/billing/change-plan/confirm", json={"offerKey": "premium_monthly", "previewToken": "x"}
    )
    assert response.status_code in (401, 403)


def test_cancel_scheduled_anonymous_rejected():
    response = client.post("/billing/change-plan/cancel-scheduled", json={})
    assert response.status_code in (401, 403)


def test_preview_success(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        assert user_id == "user-1"
        assert offer_key == "premium_monthly"
        return {"action": "upgrade_now", "fromPlan": "plus", "toPlan": "premium", "amountDueNow": 1500, "previewToken": "tok"}

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)

    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "premium_monthly"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    assert response.status_code == 200
    assert response.json()["amountDueNow"] == 1500


def test_preview_not_allowed_maps_to_409(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        raise PlanChangeNotAllowed("not allowed")

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)

    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "plus_annual"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    assert response.status_code == 409


def test_preview_ownership_error_maps_to_403(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        raise BillingOwnershipError("no mapping")

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)

    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "premium_monthly"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    assert response.status_code == 403


def test_confirm_preview_stale_maps_to_409(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_confirm(self, *, user_id, offer_key, preview_token):
        raise PlanChangePreviewStale("stale")

    monkeypatch.setattr(billing_service_module.BillingService, "confirm_plan_change", fake_confirm)

    response = client.post(
        "/billing/change-plan/confirm",
        json={"offerKey": "premium_monthly", "previewToken": "tok"},
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_CHANGE_PREVIEW_STALE"


def test_confirm_ignores_extra_browser_supplied_fields(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    captured = {}

    def fake_confirm(self, *, user_id, offer_key, preview_token):
        captured["user_id"] = user_id
        captured["offer_key"] = offer_key
        return {"action": "upgrade_now", "paymentResult": "succeeded"}

    monkeypatch.setattr(billing_service_module.BillingService, "confirm_plan_change", fake_confirm)

    response = client.post(
        "/billing/change-plan/confirm",
        json={
            "offerKey": "premium_monthly",
            "previewToken": "tok",
            "subscriptionId": "sub_attacker_controlled",
            "userId": "someone-else",
            "amountDueNow": 1,
        },
        headers=_auth_headers(monkeypatch, "user-1"),
    )
    assert response.status_code == 200
    assert captured["user_id"] == "user-1"  # server-resolved from auth, not from body


def test_cancel_scheduled_success(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_cancel(self, *, user_id):
        return {"cancelled": True}

    monkeypatch.setattr(billing_service_module.BillingService, "cancel_scheduled_plan_change", fake_cancel)

    response = client.post(
        "/billing/change-plan/cancel-scheduled", json={}, headers=_auth_headers(monkeypatch, "user-1")
    )
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
