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
    # Without this, real Stripe returns `latest_invoice` as a bare invoice-ID
    # string rather than the expanded object -- confirmed against a real
    # Stripe sandbox upgrade during the full application E2E test, where this
    # caused _normalize_payment_result to misreport "requires_action" on an
    # invoice that had actually been paid synchronously and successfully.
    assert params["expand"] == ["latest_invoice.payment_intent"]
    assert options == {"idempotency_key": "planchange:sub_1:price_a:price_target:1735689600"}


def test_update_subscription_item_misreads_unexpanded_invoice_as_requires_action_without_expand():
    """Regression test for the real bug: if Stripe were ever called without
    requesting expansion, `latest_invoice` comes back as a bare id string.
    `_normalize_payment_result` must not silently misread that as
    "requires_action" -- this test pins the actual (bug) behavior against the
    real shape Stripe returns, so the params["expand"] assertion above is the
    thing that actually prevents it in production, not a change to
    _normalize_payment_result itself (which correctly trusts its input)."""
    from backend.domain.billing.providers.stripe_provider import _normalize_payment_result

    # This is the literal shape stripe-python returns when latest_invoice is
    # NOT expanded: a bare string, not a dict/object.
    unexpanded_subscription = {"latest_invoice": "in_1UBHt07OgvEwKwH3W4pHDkvB"}
    assert _normalize_payment_result(unexpanded_subscription) == "requires_action"

    # The fix: with the real expanded shape (what params["expand"] above
    # guarantees the real API call requests), the true "paid" status is seen.
    expanded_subscription = {"latest_invoice": {"status": "paid", "payment_intent": None}}
    assert _normalize_payment_result(expanded_subscription) == "succeeded"


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
    # The create call's idempotency key is namespaced by the caller-supplied
    # base key but suffixed with a fresh per-call nonce -- confirmed against
    # a real Stripe sandbox that a purely input-derived (stable-for-a-whole-
    # billing-period) key causes Stripe to replay a stale cached response
    # (the first, possibly since-released, schedule) on any later legitimate
    # re-attempt with the same inputs, rather than creating a fresh schedule.
    assert create_options["idempotency_key"].startswith("plandowngrade:sub_1:price_a:price_plus_monthly:1738368000:")
    assert create_options["idempotency_key"] != "plandowngrade:sub_1:price_a:price_plus_monthly:1738368000"
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
    # The update call's idempotency key is scoped to this specific schedule's
    # own (globally unique) id, not the base key -- Stripe scopes idempotency
    # keys per endpoint and rejects reuse of the same key across
    # /v1/subscription_schedules (create) and /v1/subscription_schedules/{id}
    # (update) with IdempotencyError, as discovered against the real sandbox.
    assert update_options == {"idempotency_key": "sub_sched_1:phase2"}


def test_create_downgrade_schedule_uses_a_fresh_create_key_on_each_call():
    """Two calls with the identical caller-supplied idempotency_key (e.g. a
    legitimate schedule -> release -> schedule-again sequence within the same
    billing period, where subscription/prices/period_end are all unchanged)
    must not send the same key to Stripe's create endpoint twice -- doing so
    would replay the first call's cached response instead of creating a
    fresh schedule."""

    class Schedules:
        def __init__(self):
            self.create_calls = []

        def create(self, params, options=None):
            self.create_calls.append(options)
            return {"id": "sub_sched_1", "phases": [{"items": [{"price": "price_a"}]}]}

        def update(self, schedule_id, params, options=None):
            return {"id": schedule_id}

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    same_base_key = "plandowngrade:sub_1:price_a:price_plus_monthly:1738368000"
    provider.create_downgrade_schedule(
        subscription_id="sub_1", target_price_id="price_plus_monthly",
        current_period_end=1738368000, idempotency_key=same_base_key,
    )
    provider.create_downgrade_schedule(
        subscription_id="sub_1", target_price_id="price_plus_monthly",
        current_period_end=1738368000, idempotency_key=same_base_key,
    )

    first_key = schedules.create_calls[0]["idempotency_key"]
    second_key = schedules.create_calls[1]["idempotency_key"]
    assert first_key != second_key
    assert first_key.startswith(same_base_key)
    assert second_key.startswith(same_base_key)


def test_create_downgrade_schedule_projects_phase1_to_writable_subset_only():
    """A 'rich' create response can carry read-only/expanded fields (e.g. a
    fully expanded price object, or extra computed keys with no writable
    counterpart at all). The resubmitted phase-1 payload must contain
    `collection_method` (a real writable field, correctly preserved) but
    must NOT contain `proration_behavior` (a read-only-ish computed field
    with no equivalent in the writable phase schema)."""

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
                        "proration_behavior": "none",  # not a writable phase field; must not survive projection
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
        "collection_method": "charge_automatically",
    }
    assert "proration_behavior" not in phase1


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


def test_create_downgrade_schedule_preserves_active_discount():
    """An active discount on the current phase must be carried forward into
    the resubmitted phase-1 payload as a `{"discount": <id>}` reference, not
    silently dropped."""

    class Schedules:
        def __init__(self):
            self.update_calls = []

        def create(self, params, options=None):
            return {
                "id": "sub_sched_1",
                "phases": [
                    {
                        "items": [{"price": "price_a", "quantity": 1}],
                        "start_date": 1735689600,
                        "end_date": 1738368000,
                        "discounts": [{"id": "di_active_coupon", "object": "discount", "coupon": {"id": "co_1"}}],
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
    assert phase1["discounts"] == [{"discount": "di_active_coupon"}]


def test_create_downgrade_schedule_preserves_default_tax_rates_and_collection_method():
    class Schedules:
        def __init__(self):
            self.update_calls = []

        def create(self, params, options=None):
            return {
                "id": "sub_sched_1",
                "phases": [
                    {
                        "items": [{"price": "price_a", "quantity": 1}],
                        "start_date": 1735689600,
                        "end_date": 1738368000,
                        "default_tax_rates": [{"id": "txr_1", "object": "tax_rate"}],
                        "collection_method": "send_invoice",
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
    assert phase1["default_tax_rates"] == ["txr_1"]
    assert phase1["collection_method"] == "send_invoice"


def test_create_downgrade_schedule_fails_closed_on_unrepresentable_discount_and_releases_schedule():
    """If a discount cannot be reduced to a resource id (unexpected shape),
    the schedule must fail closed -- PlanChangeNotAllowed, not a silent drop
    -- and the schedule created by the earlier `create` call must be
    released so the subscription is left exactly as it was found."""
    from backend.domain.billing.errors import PlanChangeNotAllowed

    class Schedules:
        def __init__(self):
            self.release_calls = []

        def create(self, params, options=None):
            return {
                "id": "sub_sched_1",
                "phases": [
                    {
                        "items": [{"price": "price_a", "quantity": 1}],
                        "start_date": 1735689600,
                        "end_date": 1738368000,
                        "discounts": [{"object": "discount"}],  # no resolvable id
                    }
                ],
            }

        def update(self, schedule_id, params, options=None):
            raise AssertionError("update must not be called when phase-1 projection fails closed")

        def release(self, schedule_id):
            self.release_calls.append(schedule_id)

    schedules = Schedules()
    provider = StripeProvider(secret_key="nonempty-test-key")
    provider.client = _client_with(schedules=schedules)

    with pytest.raises(PlanChangeNotAllowed):
        provider.create_downgrade_schedule(
            subscription_id="sub_1", target_price_id="price_plus_monthly",
            current_period_end=1738368000, idempotency_key="key_1",
        )

    assert schedules.release_calls == ["sub_sched_1"]
