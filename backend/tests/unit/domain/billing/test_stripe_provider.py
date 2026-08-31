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
