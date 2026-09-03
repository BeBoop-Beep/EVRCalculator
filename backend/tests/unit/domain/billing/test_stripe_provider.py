import pytest
from backend.domain.billing.errors import BillingNotConfigured, InvalidWebhookSignature
from backend.domain.billing.providers.stripe_provider import StripeProvider

def test_provider_fails_without_backend_secret():
    with pytest.raises(BillingNotConfigured): StripeProvider(secret_key="").retrieve_subscription("sub_x")

def test_webhook_missing_configuration_fails_closed():
    with pytest.raises(BillingNotConfigured): StripeProvider(secret_key="nonempty-test-key", webhook_secret="").construct_event(b"{}", "sig")

def test_invalid_signature_is_controlled():
    with pytest.raises(InvalidWebhookSignature):
        StripeProvider(secret_key="nonempty-test-key", webhook_secret="nonempty-test-webhook-secret").construct_event(b"{}", "bad")

def test_checkout_uses_managed_payments_without_automatic_tax_promotions_or_trial():
    captured = {}
    class Sessions:
        def create(self, params): captured.update(params); return {"url": "https://example.test"}
    class Client: pass
    client = Client(); client.v1 = Client(); client.v1.checkout = Client(); client.v1.checkout.sessions = Sessions()
    provider = StripeProvider(secret_key="nonempty-test-key"); provider.client = client
    provider.create_checkout_session(customer_id="cus_1", price_id="price_1", user_id="u1",
        offer_key="plus_monthly", plan="plus", success_url="https://example.test/s",
        cancel_url="https://example.test/c")
    assert captured["allow_promotion_codes"] is False
    assert captured["managed_payments"] == {"enabled": True}
    assert captured["consent_collection"] == {"terms_of_service": "required"}
    assert "automatic_tax" not in captured
    assert "trial_period_days" not in captured["subscription_data"]
    assert "trial_end" not in captured["subscription_data"]
    assert captured["line_items"] == [{"price": "price_1", "quantity": 1}]
    assert set(captured) == {
        "mode", "customer", "line_items", "managed_payments",
        "allow_promotion_codes", "consent_collection", "success_url", "cancel_url",
        "client_reference_id", "metadata", "subscription_data",
    }
