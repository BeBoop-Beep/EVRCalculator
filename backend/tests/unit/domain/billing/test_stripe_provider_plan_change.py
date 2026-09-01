import pytest
from backend.domain.billing.providers.stripe_provider import StripeProvider


class _Obj:
    pass


def _client_with(invoices=None, subscriptions=None, schedules=None):
    client = _Obj()
    client.v1 = _Obj()
    client.v1.invoices = invoices if invoices is not None else _Obj()
    client.v1.subscriptions = subscriptions if subscriptions is not None else _Obj()
    client.v1.subscription_schedules = schedules if schedules is not None else _Obj()
    return client


def test_preview_subscription_update_returns_normalized_amount():
    class Invoices:
        def create_preview(self, params, **kwargs):
            self.captured = params
            return {"amount_due": 1500, "currency": "usd"}

    invoices = Invoices()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(invoices=invoices)

    result = provider.preview_subscription_update(
        subscription_id="sub_1",
        subscription_item_id="si_1",
        target_price_id="price_target",
        proration_date=1735689600,
    )

    assert result == {"amount_due": 1500, "currency": "usd"}
    assert invoices.captured["subscription"] == "sub_1"
    assert invoices.captured["subscription_details"]["items"] == [
        {"id": "si_1", "price": "price_target"}
    ]
    assert invoices.captured["subscription_details"]["proration_behavior"] == "always_invoice"
    assert invoices.captured["subscription_details"]["proration_date"] == 1735689600


def test_update_subscription_item_passes_idempotency_key_and_normalizes_success():
    class Subscriptions:
        def update(self, subscription_id, params, options=None):
            self.captured = (subscription_id, params, options)
            return {"latest_invoice": {"payment_intent": {"status": "succeeded"}}}

    subscriptions = Subscriptions()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(subscriptions=subscriptions)

    result = provider.update_subscription_item(
        subscription_id="sub_1",
        subscription_item_id="si_1",
        target_price_id="price_target",
        proration_date=1735689600,
        idempotency_key="planchange:sub_1:price_a:price_target:1735689600",
    )

    assert result["payment_result"] == "succeeded"
    assert result["subscription"] == {"latest_invoice": {"payment_intent": {"status": "succeeded"}}}
    call_id, params, options = subscriptions.captured
    assert call_id == "sub_1"
    assert params["items"] == [{"id": "si_1", "price": "price_target"}]
    assert params["proration_behavior"] == "always_invoice"
    assert params["proration_date"] == 1735689600
    assert params["payment_behavior"] == "pending_if_incomplete"
    assert options == {"idempotency_key": "planchange:sub_1:price_a:price_target:1735689600"}


def test_update_subscription_item_normalizes_requires_action():
    class Subscriptions:
        def update(self, subscription_id, params, options=None):
            return {"latest_invoice": {"payment_intent": {"status": "requires_action"}}}

    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(subscriptions=Subscriptions())

    result = provider.update_subscription_item(
        subscription_id="sub_1", subscription_item_id="si_1", target_price_id="price_target",
        proration_date=1735689600, idempotency_key="key_1",
    )

    assert result["payment_result"] == "requires_action"


def test_update_subscription_item_normalizes_failed():
    class Subscriptions:
        def update(self, subscription_id, params, options=None):
            return {"latest_invoice": {"payment_intent": {"status": "requires_payment_method"}}}

    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(subscriptions=Subscriptions())

    result = provider.update_subscription_item(
        subscription_id="sub_1", subscription_item_id="si_1", target_price_id="price_target",
        proration_date=1735689600, idempotency_key="key_1",
    )

    assert result["payment_result"] == "failed"


def test_create_downgrade_schedule_builds_from_subscription():
    class Schedules:
        def __init__(self):
            self.create_calls = []
            self.update_calls = []

        def create(self, params, options=None):
            self.create_calls.append((params, options))
            return {"id": "sub_sched_1", "phases": [{"items": [{"price": "price_a"}]}]}

        def update(self, schedule_id, params, options=None):
            self.update_calls.append((schedule_id, params, options))
            return {"id": "sub_sched_1", "phases": [{"items": [{"price": "price_a"}]}, params["phases"][1]]}

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    result = provider.create_downgrade_schedule(
        subscription_id="sub_1",
        target_price_id="price_plus_monthly",
        current_period_end=1738368000,
        idempotency_key="plandowngrade:sub_1:price_a:price_plus_monthly:1738368000",
    )

    assert result["id"] == "sub_sched_1"
    create_params, create_options = schedules.create_calls[0]
    assert create_params == {"from_subscription": "sub_1"}
    assert create_options == {"idempotency_key": "plandowngrade:sub_1:price_a:price_plus_monthly:1738368000"}
    update_schedule_id, update_params, update_options = schedules.update_calls[0]
    assert update_schedule_id == "sub_sched_1"
    assert update_params["end_behavior"] == "release"
    # Phase 1 is projected to the writable subset (items/start_date/end_date),
    # not resubmitted verbatim from the `create` response.
    assert update_params["phases"][0] == {
        "items": [{"price": "price_a", "quantity": 1}],
        "start_date": None,
        "end_date": 1738368000,
    }
    assert update_params["phases"][1] == {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000}
    assert update_options == {"idempotency_key": "plandowngrade:sub_1:price_a:price_plus_monthly:1738368000"}


def test_create_downgrade_schedule_projects_phase1_to_writable_subset_only():
    """A 'rich' create response can carry read-only/expanded fields (e.g. a
    fully expanded price object, or extra computed keys). The resubmitted
    phase-1 payload must contain only the documented-writable subset, not
    those extra keys."""

    class Schedules:
        def __init__(self):
            self.update_calls = []

        def create(self, params, options=None):
            return {
                "id": "sub_sched_1",
                "phases": [
                    {
                        "items": [{"price": {"id": "price_a", "object": "price", "unit_amount": 999}, "quantity": 2}],
                        "start_date": 1735689600,
                        "end_date": 1738368000,
                        "proration_behavior": "none",  # read-only-ish extra field that must not survive projection
                        "collection_method": "charge_automatically",
                    }
                ],
            }

        def update(self, schedule_id, params, options=None):
            self.update_calls.append((schedule_id, params, options))
            return {"id": "sub_sched_1"}

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    provider.create_downgrade_schedule(
        subscription_id="sub_1", target_price_id="price_plus_monthly",
        current_period_end=1738368000, idempotency_key="key_1",
    )

    phase1 = schedules.update_calls[0][1]["phases"][0]
    assert phase1 == {
        "items": [{"price": "price_a", "quantity": 2}],
        "start_date": 1735689600,
        "end_date": 1738368000,
    }
    assert set(phase1.keys()) == {"items", "start_date", "end_date"}


def test_create_downgrade_schedule_releases_schedule_when_second_call_fails():
    class Schedules:
        def __init__(self):
            self.release_calls = []

        def create(self, params, options=None):
            return {"id": "sub_sched_1", "phases": [{"items": [{"price": "price_a"}]}]}

        def update(self, schedule_id, params, options=None):
            raise RuntimeError("simulated Stripe rejection")

        def release(self, schedule_id):
            self.release_calls.append(schedule_id)

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    from backend.domain.billing.errors import BillingProviderError

    with pytest.raises(BillingProviderError):
        provider.create_downgrade_schedule(
            subscription_id="sub_1", target_price_id="price_plus_monthly",
            current_period_end=1738368000, idempotency_key="key_1",
        )

    assert schedules.release_calls == ["sub_sched_1"]


def test_release_schedule_calls_release():
    class Schedules:
        def __init__(self):
            self.release_calls = []

        def release(self, schedule_id):
            self.release_calls.append(schedule_id)

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    provider.release_schedule(schedule_id="sub_sched_1")

    assert schedules.release_calls == ["sub_sched_1"]


def test_preview_subscription_update_requires_configured_client():
    provider = StripeProvider(secret_key="")
    from backend.domain.billing.errors import BillingNotConfigured

    with pytest.raises(BillingNotConfigured):
        provider.preview_subscription_update(
            subscription_id="sub_1", subscription_item_id="si_1",
            target_price_id="price_target", proration_date=1735689600,
        )
