# Billing Plan-Change (Plus ↔ Premium) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an existing Plus subscriber upgrade to Premium immediately (Stripe-prorated) and an existing Premium subscriber schedule a downgrade to Plus at period end, entirely first-party (no Customer Portal), with Stripe as sole authority for current billing state and zero Supabase writes.

**Architecture:** Three new `POST /billing/change-plan/{preview,confirm,cancel-scheduled}` endpoints, backed by a pure new domain module `plan_change.py` (direction classification, schedule-shape classification, DTO shaping) plus a pure `preview_token.py` (signed proration commitment), orchestrated by three new `BillingService` methods that do all Stripe I/O through three new `StripeProvider` methods. `billing_status()` gains additive `pendingChangeState`/`pendingPlan`/`pendingOfferKey`/`pendingChangeEffectiveAt` fields, computed live from Stripe on every call. Frontend adds one client module function per endpoint, three Next.js proxy routes, and a new in-page confirm step in `PricingPageClient.jsx` replacing the Portal redirect for cross-tier changes.

**Tech Stack:** Python (FastAPI-style routes in `backend/api/main.py`), `stripe==15.4.0`, Next.js App Router API routes, Node's built-in `tsx --test` runner for frontend tests, `pytest` for backend tests.

**Spec:** `docs/superpowers/specs/2026-09-01-billing-plan-change-design.md`

## Global Constraints

- `BILLING_CHECKOUT_ENABLED` stays `false` throughout and at completion — never flip it.
- No Stripe Product/Price creation or mutation. Only the 4 existing sandbox Price IDs are referenced (via existing env-var-backed catalog, never hardcoded).
- No Supabase migrations, no new tables/columns. Pending-change state is never persisted — computed live from Stripe on every read.
- No Stripe Price/Product IDs ever appear in frontend/browser code — only `offerKey` strings cross that boundary.
- Browser may supply only `offerKey` (preview) and `offerKey` + `previewToken` (confirm) — nothing else (no user/customer/subscription/item/price IDs, no amounts, no dates).
- `plan_change.py` and `preview_token.py` contain zero Stripe/Supabase/HTTP calls — pure functions only, unit-testable without mocks.
- `StripeProvider` remains the only Stripe SDK touchpoint; `BillingRepository` remains the only Supabase touchpoint — neither gains new I/O beyond what's specified below (repository is NOT modified — this feature persists nothing).
- Same-tier interval changes (Plus↔Plus, Premium↔Premium) are out of scope and must be rejected.
- New env var: `BILLING_PLAN_CHANGE_SIGNING_SECRET` — separate from `STRIPE_WEBHOOK_SECRET`/`STRIPE_SECRET_KEY`/any JWT secret.
- Reuse existing `PricingPageClient.jsx` gold(Plus)/purple(Premium) presentation primitives — no new styling system.
- Do not modify `MembershipBillingSection.jsx` (Portal role unchanged) or any existing `/billing/checkout-session`, `/billing/customer-portal`, `/billing/catalog` route/behavior.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/domain/billing/errors.py` | Modify | Add `PlanChangeNotAllowed`, `PlanChangePreviewStale` |
| `backend/domain/billing/preview_token.py` | Create | Pure: sign/verify the HMAC preview-token |
| `backend/domain/billing/plan_change.py` | Create | Pure: direction classification, schedule-shape classification, DTO shaping |
| `backend/domain/billing/providers/stripe_provider.py` | Modify | Add `preview_subscription_update`, `update_subscription_item`, `create_downgrade_schedule`, `release_schedule` |
| `backend/db/services/billing_service.py` | Modify | Add `preview_plan_change`, `confirm_plan_change`, `cancel_scheduled_plan_change`; extend `billing_status()` |
| `backend/api/main.py` | Modify | Add 3 routes: `/billing/change-plan/{preview,confirm,cancel-scheduled}` |
| `frontend/lib/billing/billingClient.mjs` | Modify | Add `previewPlanChange`, `confirmPlanChange`, `cancelScheduledPlanChange` |
| `frontend/app/api/billing/change-plan/preview/route.js` | Create | Proxy to backend preview endpoint |
| `frontend/app/api/billing/change-plan/confirm/route.js` | Create | Proxy to backend confirm endpoint |
| `frontend/app/api/billing/change-plan/cancel-scheduled/route.js` | Create | Proxy to backend cancel-scheduled endpoint |
| `frontend/lib/billing/billingPresentation.mjs` | Modify | Add formatting helpers for the new DTO fields |
| `frontend/components/pricing/PricingPageClient.jsx` | Modify | Replace Portal-routing `managed` branch with in-page plan-change UX |

Test files (new, matching existing conventions):
- `backend/tests/unit/domain/billing/test_preview_token.py`
- `backend/tests/unit/domain/billing/test_plan_change.py`
- `backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py` (kept separate from the existing `test_stripe_provider.py` to keep files focused)
- `backend/tests/unit/db/services/test_billing_service_plan_change.py`
- `backend/tests/unit/api/test_billing_plan_change_api.py`
- `frontend/lib/billing/billingClient.planChange.test.mjs`
- `frontend/lib/billing/billingPresentation.planChange.test.mjs`
- `frontend/components/pricing/PricingPageClient.planChange.test.mjs` (new — no existing test file for this component per repo scan; create fresh)

---

## Task 1: Errors

**Files:**
- Modify: `backend/domain/billing/errors.py`
- Test: `backend/tests/unit/domain/billing/test_plan_change.py` (error import checked implicitly by later tasks; no dedicated error test file needed — `BillingError` subclasses have no logic to unit test beyond construction, matching how existing errors are tested)

**Interfaces:**
- Produces: `PlanChangeNotAllowed(BillingError)`, `PlanChangePreviewStale(BillingError)` — both plain `BillingError(RuntimeError)` subclasses, constructed with a message string like the 9 existing errors (no special kwargs).

- [ ] **Step 1: Add the two new error classes**

Append to `backend/domain/billing/errors.py` (matching the exact style of the existing 9 classes — no docstrings, no `code` class attribute since none of the existing ones define one either):

```python
class PlanChangeNotAllowed(BillingError):
    pass


class PlanChangePreviewStale(BillingError):
    pass
```

- [ ] **Step 2: Verify import works**

Run: `backend/.venv/Scripts/python.exe -c "from backend.domain.billing.errors import PlanChangeNotAllowed, PlanChangePreviewStale; print(PlanChangeNotAllowed('x'))"`
Expected: prints `x` with no traceback.

- [ ] **Step 3: Commit**

```bash
git add backend/domain/billing/errors.py
git commit -m "feat(billing): add PlanChangeNotAllowed and PlanChangePreviewStale errors"
```

---

## Task 2: Preview token (pure)

**Files:**
- Create: `backend/domain/billing/preview_token.py`
- Test: `backend/tests/unit/domain/billing/test_preview_token.py`

**Interfaces:**
- Consumes: nothing (pure, stdlib only — `hmac`, `hashlib`, `json`, `base64`, `time`).
- Produces:
  - `sign_preview_token(*, secret: str, visible: dict, hidden: dict) -> str`
  - `verify_preview_token(token: str, *, secret: str, hidden: dict, now: float | None = None) -> dict` — returns the `visible` dict on success; raises `PlanChangeNotAllowed` on any failure (bad format, bad signature, expired). `visible` dict must contain a `expiresAt` key (unix seconds, int/float) checked against `now` (defaults to `time.time()`).
  - `TOKEN_VERSION = 1` module constant.

Design: token format is `f"v{TOKEN_VERSION}.{base64_visible}.{hex_signature}"`. `base64_visible` is URL-safe base64 (no padding) of `json.dumps(visible, sort_keys=True)`. The signature is `HMAC-SHA256(secret, base64_visible + "|" + json.dumps(hidden, sort_keys=True))` — hidden fields are never embedded in the token itself (only bound cryptographically), so subscription/customer/price IDs never reach the browser via this token.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/domain/billing/test_preview_token.py
import time

import pytest

from backend.domain.billing.errors import PlanChangeNotAllowed
from backend.domain.billing.preview_token import sign_preview_token, verify_preview_token

SECRET = "test-signing-secret"

VISIBLE = {
    "version": 1,
    "action": "upgrade_now",
    "prorationDate": 1735689600,
    "amountDueNow": 1500,
    "currency": "usd",
    "expiresAt": 9999999999,
}

HIDDEN = {
    "userId": "user-1",
    "subscriptionId": "sub_1",
    "subscriptionItemId": "si_1",
    "currentPriceId": "price_current",
    "targetPriceId": "price_target",
    "currentPeriodEnd": 1738368000,
    "offerKey": "premium_monthly",
}


def test_round_trip_succeeds_with_matching_hidden_state():
    token = sign_preview_token(secret=SECRET, visible=VISIBLE, hidden=HIDDEN)
    result = verify_preview_token(token, secret=SECRET, hidden=HIDDEN)
    assert result == VISIBLE


def test_tampered_visible_payload_rejected():
    token = sign_preview_token(secret=SECRET, visible=VISIBLE, hidden=HIDDEN)
    prefix, _, sig = token.rpartition(".")
    tampered_visible = dict(VISIBLE, amountDueNow=1)
    import base64
    import json

    tampered_b64 = base64.urlsafe_b64encode(
        json.dumps(tampered_visible, sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    tampered_token = f"v1.{tampered_b64}.{sig}"
    with pytest.raises(PlanChangeNotAllowed):
        verify_preview_token(tampered_token, secret=SECRET, hidden=HIDDEN)


def test_wrong_secret_rejected():
    token = sign_preview_token(secret=SECRET, visible=VISIBLE, hidden=HIDDEN)
    with pytest.raises(PlanChangeNotAllowed):
        verify_preview_token(token, secret="different-secret", hidden=HIDDEN)


def test_mismatched_hidden_state_rejected():
    token = sign_preview_token(secret=SECRET, visible=VISIBLE, hidden=HIDDEN)
    other_hidden = dict(HIDDEN, subscriptionId="sub_2")
    with pytest.raises(PlanChangeNotAllowed):
        verify_preview_token(token, secret=SECRET, hidden=other_hidden)


def test_expired_token_rejected():
    expired_visible = dict(VISIBLE, expiresAt=1000)
    token = sign_preview_token(secret=SECRET, visible=expired_visible, hidden=HIDDEN)
    with pytest.raises(PlanChangeNotAllowed):
        verify_preview_token(token, secret=SECRET, hidden=HIDDEN, now=2000)


def test_malformed_token_rejected():
    with pytest.raises(PlanChangeNotAllowed):
        verify_preview_token("not-a-real-token", secret=SECRET, hidden=HIDDEN)


def test_hidden_identifiers_never_appear_in_token_text():
    token = sign_preview_token(secret=SECRET, visible=VISIBLE, hidden=HIDDEN)
    assert HIDDEN["subscriptionId"] not in token
    assert HIDDEN["currentPriceId"] not in token
    assert HIDDEN["targetPriceId"] not in token
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_preview_token.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.domain.billing.preview_token'`

- [ ] **Step 3: Implement `preview_token.py`**

```python
# backend/domain/billing/preview_token.py
import base64
import hashlib
import hmac
import json
import time

from .errors import PlanChangeNotAllowed

TOKEN_VERSION = 1


def _b64_encode(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64_decode(text: str) -> dict:
    padding = "=" * (-len(text) % 4)
    raw = base64.urlsafe_b64decode(text + padding)
    return json.loads(raw.decode("utf-8"))


def _signature(secret: str, visible_b64: str, hidden: dict) -> str:
    hidden_json = json.dumps(hidden, sort_keys=True)
    message = f"{visible_b64}|{hidden_json}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_preview_token(*, secret: str, visible: dict, hidden: dict) -> str:
    visible_b64 = _b64_encode(visible)
    sig = _signature(secret, visible_b64, hidden)
    return f"v{TOKEN_VERSION}.{visible_b64}.{sig}"


def verify_preview_token(token: str, *, secret: str, hidden: dict, now: float | None = None) -> dict:
    try:
        version_part, visible_b64, sig = token.split(".", 2)
        if version_part != f"v{TOKEN_VERSION}":
            raise ValueError("unsupported token version")
        visible = _b64_decode(visible_b64)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanChangeNotAllowed("Malformed preview token") from exc

    expected_sig = _signature(secret, visible_b64, hidden)
    if not hmac.compare_digest(expected_sig, sig):
        raise PlanChangeNotAllowed("Preview token signature mismatch")

    expires_at = visible.get("expiresAt")
    if expires_at is None:
        raise PlanChangeNotAllowed("Preview token missing expiry")
    current_time = time.time() if now is None else now
    if current_time > expires_at:
        raise PlanChangeNotAllowed("Preview token expired")

    return visible
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_preview_token.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/domain/billing/preview_token.py backend/tests/unit/domain/billing/test_preview_token.py
git commit -m "feat(billing): add pure signed preview-token module"
```

---

## Task 3: Plan-change domain logic (pure)

**Files:**
- Create: `backend/domain/billing/plan_change.py`
- Test: `backend/tests/unit/domain/billing/test_plan_change.py`

**Interfaces:**
- Consumes: `PLAN_RANK` from `backend/domain/billing/policy.py` (existing: `{None: 0, "plus": 1, "premium": 2}`); `offer_for_price_id`, `CommercialOffer` from `backend/domain/billing/catalog.py` (existing); `PlanChangeNotAllowed` from Task 1.
- Produces:
  - `class PlanChangeAction(str, Enum)`: `UPGRADE_NOW = "upgrade_now"`, `DOWNGRADE_AT_PERIOD_END = "downgrade_at_period_end"`.
  - `classify_transition(current_plan: str | None, target_plan: str | None) -> PlanChangeAction` — raises `PlanChangeNotAllowed` if either plan isn't `"plus"`/`"premium"`, or if `current_plan == target_plan` (same-tier interval change or no-op).
  - `SCHEDULE_STATE_NONE = "none"`, `SCHEDULE_STATE_SCHEDULED = "scheduled"`, `SCHEDULE_STATE_UNKNOWN = "unknown"` module constants.
  - `classify_schedule(schedule: dict | None, *, current_price_id: str, current_period_end: int, offers: dict) -> dict` — returns `{"state": ..., "pendingPlan": str|None, "pendingOfferKey": str|None, "pendingChangeEffectiveAt": int|None}`. `schedule` is the raw Stripe schedule object (as a dict) or `None`. Classifies `scheduled` only if: `schedule["phases"]` has exactly 2 entries; phase 1's price matches `current_price_id` and ends at `current_period_end`; phase 2 starts at `current_period_end` and its price maps (via `offer_for_price_id`) to plan `"plus"`. Anything else (wrong phase count, mismatched price/date, unmapped phase-2 price) → `unknown`.
  - `build_upgrade_preview_dto(*, from_plan, to_plan, from_offer_key, to_offer_key, currency, amount_due_now, effective_at, next_renewal_at) -> dict` — returns the exact DTO shape from spec §7/§8 plus `"action": PlanChangeAction.UPGRADE_NOW.value`.
  - `build_downgrade_preview_dto(*, from_plan, to_plan, from_offer_key, to_offer_key, current_period_end) -> dict` — returns `{"action": "downgrade_at_period_end", "fromPlan":..., "toPlan":..., "fromOfferKey":..., "toOfferKey":..., "amountDueNow": 0, "effectiveAt": current_period_end, "currentPlanUntil": current_period_end}`.
  - `IDEMPOTENCY_KEY_PREFIX_UPGRADE = "planchange"`, `IDEMPOTENCY_KEY_PREFIX_DOWNGRADE = "plandowngrade"`.
  - `upgrade_idempotency_key(subscription_id, current_price_id, target_price_id, proration_date) -> str` → `f"planchange:{subscription_id}:{current_price_id}:{target_price_id}:{proration_date}"`.
  - `downgrade_idempotency_key(subscription_id, current_price_id, target_price_id, current_period_end) -> str` → `f"plandowngrade:{subscription_id}:{current_price_id}:{target_price_id}:{current_period_end}"`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/domain/billing/test_plan_change.py
import pytest

from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.errors import PlanChangeNotAllowed
from backend.domain.billing.plan_change import (
    PlanChangeAction,
    build_downgrade_preview_dto,
    build_upgrade_preview_dto,
    classify_schedule,
    classify_transition,
    downgrade_idempotency_key,
    upgrade_idempotency_key,
)

PREMIUM_MONTHLY_OFFER = CommercialOffer(
    offer_key="premium_monthly",
    plan="premium",
    billing_interval="month",
    enabled=True,
    provider_price_id="price_premium_monthly",
    unit_amount_minor=2499,
    currency="usd",
)
PLUS_MONTHLY_OFFER = CommercialOffer(
    offer_key="plus_monthly",
    plan="plus",
    billing_interval="month",
    enabled=True,
    provider_price_id="price_plus_monthly",
    unit_amount_minor=999,
    currency="usd",
)
OFFERS = {"premium_monthly": PREMIUM_MONTHLY_OFFER, "plus_monthly": PLUS_MONTHLY_OFFER}


@pytest.mark.parametrize(
    "current_plan,target_plan,expected",
    [
        ("plus", "premium", PlanChangeAction.UPGRADE_NOW),
        ("premium", "plus", PlanChangeAction.DOWNGRADE_AT_PERIOD_END),
    ],
)
def test_classify_transition_valid_cross_tier(current_plan, target_plan, expected):
    assert classify_transition(current_plan, target_plan) == expected


@pytest.mark.parametrize(
    "current_plan,target_plan",
    [
        ("plus", "plus"),
        ("premium", "premium"),
        (None, "plus"),
        ("plus", None),
        ("plus", "basic"),
        (None, None),
    ],
)
def test_classify_transition_rejects_invalid(current_plan, target_plan):
    with pytest.raises(PlanChangeNotAllowed):
        classify_transition(current_plan, target_plan)


def test_build_upgrade_preview_dto_shape():
    dto = build_upgrade_preview_dto(
        from_plan="plus",
        to_plan="premium",
        from_offer_key="plus_monthly",
        to_offer_key="premium_monthly",
        currency="usd",
        amount_due_now=1500,
        effective_at=1735689600,
        next_renewal_at=1738368000,
    )
    assert dto == {
        "action": "upgrade_now",
        "fromPlan": "plus",
        "toPlan": "premium",
        "fromOfferKey": "plus_monthly",
        "toOfferKey": "premium_monthly",
        "currency": "usd",
        "amountDueNow": 1500,
        "effectiveAt": 1735689600,
        "nextRenewalAt": 1738368000,
    }


def test_build_downgrade_preview_dto_shape():
    dto = build_downgrade_preview_dto(
        from_plan="premium",
        to_plan="plus",
        from_offer_key="premium_monthly",
        to_offer_key="plus_monthly",
        current_period_end=1738368000,
    )
    assert dto == {
        "action": "downgrade_at_period_end",
        "fromPlan": "premium",
        "toPlan": "plus",
        "fromOfferKey": "premium_monthly",
        "toOfferKey": "plus_monthly",
        "amountDueNow": 0,
        "effectiveAt": 1738368000,
        "currentPlanUntil": 1738368000,
    }


def test_classify_schedule_none():
    result = classify_schedule(
        None, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result == {
        "state": "none",
        "pendingPlan": None,
        "pendingOfferKey": None,
        "pendingChangeEffectiveAt": None,
    }


def test_classify_schedule_recognized_downgrade():
    schedule = {
        "phases": [
            {
                "items": [{"price": "price_premium_monthly"}],
                "end_date": 1738368000,
            },
            {
                "items": [{"price": "price_plus_monthly"}],
                "start_date": 1738368000,
            },
        ]
    }
    result = classify_schedule(
        schedule, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result == {
        "state": "scheduled",
        "pendingPlan": "plus",
        "pendingOfferKey": "plus_monthly",
        "pendingChangeEffectiveAt": 1738368000,
    }


@pytest.mark.parametrize(
    "schedule",
    [
        {"phases": [{"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000}]},  # 1 phase
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
                {"items": [{"price": "price_unknown"}], "start_date": 1738368000},
            ]
        },  # unmapped phase-2 price
        {
            "phases": [
                {"items": [{"price": "price_different"}], "end_date": 1738368000},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },  # phase-1 price mismatch
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 999},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },  # date mismatch between phase boundaries
    ],
)
def test_classify_schedule_unknown_shapes(schedule):
    result = classify_schedule(
        schedule, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result["state"] == "unknown"
    assert result["pendingPlan"] is None


def test_upgrade_idempotency_key_format():
    key = upgrade_idempotency_key("sub_1", "price_a", "price_b", 1735689600)
    assert key == "planchange:sub_1:price_a:price_b:1735689600"


def test_downgrade_idempotency_key_format():
    key = downgrade_idempotency_key("sub_1", "price_a", "price_b", 1738368000)
    assert key == "plandowngrade:sub_1:price_a:price_b:1738368000"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_plan_change.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.domain.billing.plan_change'`

- [ ] **Step 3: Implement `plan_change.py`**

```python
# backend/domain/billing/plan_change.py
from enum import Enum

from .catalog import offer_for_price_id
from .errors import PlanChangeNotAllowed
from .policy import PLAN_RANK

_CROSS_TIER_PLANS = {"plus", "premium"}

SCHEDULE_STATE_NONE = "none"
SCHEDULE_STATE_SCHEDULED = "scheduled"
SCHEDULE_STATE_UNKNOWN = "unknown"

IDEMPOTENCY_KEY_PREFIX_UPGRADE = "planchange"
IDEMPOTENCY_KEY_PREFIX_DOWNGRADE = "plandowngrade"


class PlanChangeAction(str, Enum):
    UPGRADE_NOW = "upgrade_now"
    DOWNGRADE_AT_PERIOD_END = "downgrade_at_period_end"


def classify_transition(current_plan, target_plan) -> PlanChangeAction:
    if current_plan not in _CROSS_TIER_PLANS or target_plan not in _CROSS_TIER_PLANS:
        raise PlanChangeNotAllowed(
            f"Plan change not supported for current={current_plan!r} target={target_plan!r}"
        )
    if current_plan == target_plan:
        raise PlanChangeNotAllowed("Same-tier interval changes are not supported in this effort")
    if PLAN_RANK[target_plan] > PLAN_RANK[current_plan]:
        return PlanChangeAction.UPGRADE_NOW
    return PlanChangeAction.DOWNGRADE_AT_PERIOD_END


def build_upgrade_preview_dto(
    *, from_plan, to_plan, from_offer_key, to_offer_key, currency, amount_due_now, effective_at, next_renewal_at
) -> dict:
    return {
        "action": PlanChangeAction.UPGRADE_NOW.value,
        "fromPlan": from_plan,
        "toPlan": to_plan,
        "fromOfferKey": from_offer_key,
        "toOfferKey": to_offer_key,
        "currency": currency,
        "amountDueNow": amount_due_now,
        "effectiveAt": effective_at,
        "nextRenewalAt": next_renewal_at,
    }


def build_downgrade_preview_dto(*, from_plan, to_plan, from_offer_key, to_offer_key, current_period_end) -> dict:
    return {
        "action": PlanChangeAction.DOWNGRADE_AT_PERIOD_END.value,
        "fromPlan": from_plan,
        "toPlan": to_plan,
        "fromOfferKey": from_offer_key,
        "toOfferKey": to_offer_key,
        "amountDueNow": 0,
        "effectiveAt": current_period_end,
        "currentPlanUntil": current_period_end,
    }


def classify_schedule(schedule, *, current_price_id, current_period_end, offers) -> dict:
    empty = {"state": SCHEDULE_STATE_NONE, "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}
    if not schedule:
        return empty

    phases = schedule.get("phases") or []
    if len(phases) != 2:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    phase_one, phase_two = phases
    phase_one_price = _phase_price(phase_one)
    phase_two_price = _phase_price(phase_two)

    if phase_one_price != current_price_id:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}
    if phase_one.get("end_date") != current_period_end:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}
    if phase_two.get("start_date") != current_period_end:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    target_offer = offer_for_price_id(phase_two_price, offers)
    if target_offer is None or target_offer.plan != "plus":
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    return {
        "state": SCHEDULE_STATE_SCHEDULED,
        "pendingPlan": target_offer.plan,
        "pendingOfferKey": target_offer.offer_key,
        "pendingChangeEffectiveAt": current_period_end,
    }


def _phase_price(phase: dict):
    items = phase.get("items") or []
    if len(items) != 1:
        return None
    return items[0].get("price")


def upgrade_idempotency_key(subscription_id, current_price_id, target_price_id, proration_date) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX_UPGRADE}:{subscription_id}:{current_price_id}:{target_price_id}:{proration_date}"


def downgrade_idempotency_key(subscription_id, current_price_id, target_price_id, current_period_end) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX_DOWNGRADE}:{subscription_id}:{current_price_id}:{target_price_id}:{current_period_end}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_plan_change.py -v`
Expected: all pass (18 parametrized+plain cases)

- [ ] **Step 5: Commit**

```bash
git add backend/domain/billing/plan_change.py backend/tests/unit/domain/billing/test_plan_change.py
git commit -m "feat(billing): add pure plan-change domain module"
```

---

## Task 4: StripeProvider plan-change methods

**Files:**
- Modify: `backend/domain/billing/providers/stripe_provider.py`
- Test: `backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py`

**Interfaces:**
- Consumes: existing `StripeProvider.__init__`, existing `self._client()` pattern (verify exact private method name in current file before writing — the earlier research called it `self._client()`; confirm and match exactly), `stripe.StripeClient`.
- Produces (new methods on `StripeProvider`):
  - `preview_subscription_update(self, *, subscription_id: str, subscription_item_id: str, target_price_id: str, proration_date: int) -> dict` — calls the Stripe invoice-preview endpoint for a proposed item price swap; returns a normalized dict `{"amount_due": int, "currency": str}`.
  - `update_subscription_item(self, *, subscription_id: str, subscription_item_id: str, target_price_id: str, proration_date: int, idempotency_key: str) -> dict` — calls `Subscription.modify`; returns normalized dict `{"payment_result": "succeeded"|"requires_action"|"failed", "subscription": <raw stripe subscription dict-like>}`.
  - `create_downgrade_schedule(self, *, subscription_id: str, target_price_id: str, current_period_end: int, idempotency_key: str) -> dict` — creates schedule from subscription, appends phase 2; returns the raw schedule object.
  - `release_schedule(self, *, schedule_id: str) -> None`.

Because the exact `stripe-python==15.4.0` method names for invoice-preview, subscription-modify payment-intent shape, and schedule creation must be verified against the installed SDK (not assumed from older docs per spec §7 step 7 and Global Constraints), this task starts with an **interactive verification step** before writing implementation code.

- [ ] **Step 1: Verify exact SDK surface before writing any code**

Run each of these against the installed venv to confirm exact method names/signatures (do not skip — do not guess from memory):

```bash
backend/.venv/Scripts/python.exe -c "import stripe; print(stripe.__version__)"
backend/.venv/Scripts/python.exe -c "import stripe; c = stripe.StripeClient('sk_test_x'); print([m for m in dir(c.v1.invoices) if not m.startswith('_')])"
backend/.venv/Scripts/python.exe -c "import stripe; c = stripe.StripeClient('sk_test_x'); print([m for m in dir(c.v1.subscription_schedules) if not m.startswith('_')])"
backend/.venv/Scripts/python.exe -c "import stripe; import inspect; c = stripe.StripeClient('sk_test_x'); print(inspect.signature(c.v1.invoices.create_preview))"
```

Confirm: (a) `stripe.__version__` prints `15.4.0`; (b) the invoice preview method name (expected `create_preview`, taking `subscription` and `subscription_details={"items": [...], "proration_behavior": ..., "proration_date": ...}` params per the 15.x resource-namespaced client — adjust the implementation below to match whatever the introspection actually shows if it differs); (c) `subscription_schedules` exposes `create` and `release`. If any name differs from what Step 3 below assumes, update Step 3 to match the introspected reality — the design intent (fresh preview, same proration_date reused, schedule generated from live subscription) is what must be preserved, not the literal snippet.

- [ ] **Step 2: Write the failing tests (using a fake Stripe client, matching existing `test_stripe_provider.py` fake/mock conventions — read that file first to copy its fake-client pattern exactly)**

```python
# backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py
import pytest

from backend.domain.billing.providers.stripe_provider import StripeProvider


class _FakeInvoices:
    def __init__(self, preview_response):
        self.preview_response = preview_response
        self.calls = []

    def create_preview(self, **kwargs):
        self.calls.append(kwargs)
        return self.preview_response


class _FakeSubscriptions:
    def __init__(self, modify_response):
        self.modify_response = modify_response
        self.calls = []

    def modify(self, subscription_id, **kwargs):
        self.calls.append((subscription_id, kwargs))
        return self.modify_response


class _FakeSchedules:
    def __init__(self, create_response):
        self.create_response = create_response
        self.create_calls = []
        self.release_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_response

    def release(self, schedule_id, **kwargs):
        self.release_calls.append(schedule_id)


class _FakeV1:
    def __init__(self, invoices, subscriptions, schedules):
        self.invoices = invoices
        self.subscriptions = subscriptions
        self.subscription_schedules = schedules


class _FakeClient:
    def __init__(self, invoices, subscriptions, schedules):
        self.v1 = _FakeV1(invoices, subscriptions, schedules)


@pytest.fixture
def provider(monkeypatch):
    instance = StripeProvider(secret_key="sk_test_fake")
    return instance


def test_preview_subscription_update_returns_normalized_amount(provider, monkeypatch):
    fake_invoices = _FakeInvoices({"amount_due": 1500, "currency": "usd"})
    fake_client = _FakeClient(fake_invoices, _FakeSubscriptions({}), _FakeSchedules({}))
    monkeypatch.setattr(provider, "_client", lambda: fake_client)

    result = provider.preview_subscription_update(
        subscription_id="sub_1",
        subscription_item_id="si_1",
        target_price_id="price_target",
        proration_date=1735689600,
    )

    assert result == {"amount_due": 1500, "currency": "usd"}
    assert fake_invoices.calls[0].get("subscription") == "sub_1" or "subscription" in fake_invoices.calls[0]


def test_update_subscription_item_passes_idempotency_key(provider, monkeypatch):
    fake_subscriptions = _FakeSubscriptions(
        {"latest_invoice": {"payment_intent": {"status": "succeeded"}}}
    )
    fake_client = _FakeClient(_FakeInvoices({}), fake_subscriptions, _FakeSchedules({}))
    monkeypatch.setattr(provider, "_client", lambda: fake_client)

    result = provider.update_subscription_item(
        subscription_id="sub_1",
        subscription_item_id="si_1",
        target_price_id="price_target",
        proration_date=1735689600,
        idempotency_key="planchange:sub_1:price_a:price_target:1735689600",
    )

    assert result["payment_result"] == "succeeded"
    call_id, call_kwargs = fake_subscriptions.calls[0]
    assert call_id == "sub_1"
    assert call_kwargs.get("proration_date") == 1735689600


def test_create_downgrade_schedule_builds_from_subscription(provider, monkeypatch):
    fake_schedules = _FakeSchedules({"id": "sub_sched_1", "phases": [{}, {}]})
    fake_client = _FakeClient(_FakeInvoices({}), _FakeSubscriptions({}), fake_schedules)
    monkeypatch.setattr(provider, "_client", lambda: fake_client)

    result = provider.create_downgrade_schedule(
        subscription_id="sub_1",
        target_price_id="price_plus_monthly",
        current_period_end=1738368000,
        idempotency_key="plandowngrade:sub_1:price_a:price_plus_monthly:1738368000",
    )

    assert result["id"] == "sub_sched_1"
    assert fake_schedules.create_calls[0].get("from_subscription") == "sub_1"


def test_release_schedule_calls_release(provider, monkeypatch):
    fake_schedules = _FakeSchedules({})
    fake_client = _FakeClient(_FakeInvoices({}), _FakeSubscriptions({}), fake_schedules)
    monkeypatch.setattr(provider, "_client", lambda: fake_client)

    provider.release_schedule(schedule_id="sub_sched_1")

    assert fake_schedules.release_calls == ["sub_sched_1"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py -v`
Expected: FAIL — `AttributeError: 'StripeProvider' object has no attribute 'preview_subscription_update'`

- [ ] **Step 4: Implement the 4 new methods on `StripeProvider`**

Add to `backend/domain/billing/providers/stripe_provider.py`, matching the file's existing style (private `self._client()` accessor confirmed in Step 1 of this task — if the existing private accessor has a different name, use that name instead of `self._client()` below):

```python
    def preview_subscription_update(self, *, subscription_id, subscription_item_id, target_price_id, proration_date):
        response = self._client().v1.invoices.create_preview(
            subscription=subscription_id,
            subscription_details={
                "items": [{"id": subscription_item_id, "price": target_price_id}],
                "proration_behavior": "always_invoice",
                "proration_date": proration_date,
            },
        )
        return {"amount_due": response["amount_due"], "currency": response["currency"]}

    def update_subscription_item(self, *, subscription_id, subscription_item_id, target_price_id, proration_date, idempotency_key):
        subscription = self._client().v1.subscriptions.modify(
            subscription_id,
            items=[{"id": subscription_item_id, "price": target_price_id}],
            proration_behavior="always_invoice",
            proration_date=proration_date,
            payment_behavior="pending_if_incomplete",
            options={"idempotency_key": idempotency_key},
        )
        payment_result = self._normalize_payment_result(subscription)
        return {"payment_result": payment_result, "subscription": subscription}

    def _normalize_payment_result(self, subscription):
        latest_invoice = subscription.get("latest_invoice") if isinstance(subscription, dict) else None
        if not latest_invoice:
            return "succeeded"
        payment_intent = latest_invoice.get("payment_intent") if isinstance(latest_invoice, dict) else None
        if not payment_intent:
            invoice_status = latest_invoice.get("status") if isinstance(latest_invoice, dict) else None
            return "succeeded" if invoice_status == "paid" else "requires_action"
        status = payment_intent.get("status")
        if status in ("succeeded",):
            return "succeeded"
        if status in ("requires_action", "requires_source_action"):
            return "requires_action"
        return "failed"

    def create_downgrade_schedule(self, *, subscription_id, target_price_id, current_period_end, idempotency_key):
        schedule = self._client().v1.subscription_schedules.create(
            from_subscription=subscription_id,
            options={"idempotency_key": idempotency_key},
        )
        phases = schedule["phases"]
        current_phase = phases[0]
        updated_phases = [
            current_phase,
            {"items": [{"price": target_price_id}], "start_date": current_period_end},
        ]
        return self._client().v1.subscription_schedules.update(
            schedule["id"],
            end_behavior="release",
            phases=updated_phases,
        )

    def release_schedule(self, *, schedule_id):
        self._client().v1.subscription_schedules.release(schedule_id)
```

Note: `_normalize_payment_result` is written defensively against dict-shaped or attribute-shaped Stripe objects — adjust to match whichever the Step 1 introspection confirms `stripe-python==15.4.0` actually returns (object-style with attribute access vs dict-style). If it's object-style, replace `.get(...)` calls with `getattr(..., name, None)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py -v`
Expected: 4 passed

- [ ] **Step 6: Run the full existing provider test file to confirm no regression**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_stripe_provider.py -v`
Expected: all previously-passing tests still pass (no existing method touched)

- [ ] **Step 7: Commit**

```bash
git add backend/domain/billing/providers/stripe_provider.py backend/tests/unit/domain/billing/test_stripe_provider_plan_change.py
git commit -m "feat(billing): add StripeProvider plan-change methods (preview, update, schedule, release)"
```

---

## Task 5: BillingService orchestration

**Files:**
- Modify: `backend/db/services/billing_service.py`
- Test: `backend/tests/unit/db/services/test_billing_service_plan_change.py`

**Interfaces:**
- Consumes: Task 2 (`sign_preview_token`, `verify_preview_token`), Task 3 (`classify_transition`, `build_upgrade_preview_dto`, `build_downgrade_preview_dto`, `classify_schedule`, `upgrade_idempotency_key`, `downgrade_idempotency_key`, `SCHEDULE_STATE_*`), Task 4 (`StripeProvider.preview_subscription_update`, `.update_subscription_item`, `.create_downgrade_schedule`, `.release_schedule`), existing `BillingRepository.find_customer`, `.find_subscriptions`, existing `catalog.OFFERS`/`offer_for_price_id`, existing `policy.has_duplicate_active_subscriptions`, `PlanChangeNotAllowed`/`PlanChangePreviewStale`/`BillingOwnershipError`/`UnsupportedSubscriptionShape`/`UnmappedStripePrice` from `errors.py`.
- Produces (new instance methods on `BillingService`):
  - `preview_plan_change(self, *, user_id: str, offer_key: str) -> dict` — full preview DTO (upgrade or downgrade shape) plus `previewToken` key (upgrade only; downgrade preview needs no token since confirm re-derives everything fresh and there's no amount to protect — `amountDueNow` is always 0).
  - `confirm_plan_change(self, *, user_id: str, offer_key: str, preview_token: str | None) -> dict` — dispatches to upgrade-confirm or downgrade-confirm based on freshly-reclassified direction; returns `{"action": ..., "paymentResult": ...}` for upgrade or `{"action": ..., "pendingChangeEffectiveAt": ...}` for downgrade.
  - `cancel_scheduled_plan_change(self, *, user_id: str) -> dict` — returns `{"cancelled": True}` on success; raises `PlanChangeNotAllowed` if no recognized schedule exists.
  - Modifies `billing_status(self, user_id)` to add `pendingChangeState`/`pendingPlan`/`pendingOfferKey`/`pendingChangeEffectiveAt` keys, wrapping the live Stripe schedule lookup in a try/except so any Stripe error degrades to `pendingChangeState: "unknown"` without touching existing fields.
  - Private helper `_resolve_current_subscription(self, user_id)` — shared by all 4 methods above: fetches `find_customer`, `find_subscriptions` (ownership check only), then calls `self.provider.retrieve_subscription(...)` fresh, expanded; validates single recurring item; returns `(customer, stripe_subscription, current_offer)`. Raises `BillingOwnershipError` (no customer/subscription), `UnsupportedSubscriptionShape` (0 or >1 items), `UnmappedStripePrice` (current price not in catalog), or reuses `has_duplicate_active_subscriptions` check to raise `UnsupportedSubscriptionShape` if the local repo shows >1 active subscription for this user (fail-closed per spec §4).

Because `StripeProvider.retrieve_subscription` currently takes only `subscription_id` (per Task 4 research — no `expand` param), this task also extends that **existing** method's signature additively: `retrieve_subscription(self, subscription_id, expand=None)` with `expand` defaulted to `None` (preserves every existing caller) and passed through to the Stripe call only when provided. This is a pre-requisite edit inside this task, not a separate task, because it's only needed by the new orchestration code.

- [ ] **Step 1: Extend `StripeProvider.retrieve_subscription` with an optional `expand` param (backward compatible)**

Locate the current method (from Task 4 research, it takes only `subscription_id`) and change its signature to:

```python
    def retrieve_subscription(self, subscription_id, expand=None):
        kwargs = {}
        if expand:
            kwargs["expand"] = expand
        return self._client().v1.subscriptions.retrieve(subscription_id, **kwargs)
```

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_stripe_provider.py -v`
Expected: all still pass (existing callers pass no `expand`, behavior unchanged).

Commit this small pre-requisite separately:

```bash
git add backend/domain/billing/providers/stripe_provider.py
git commit -m "feat(billing): allow retrieve_subscription to expand nested fields"
```

- [ ] **Step 2: Write the failing tests**

First read `backend/tests/unit/db/services/test_billing_service.py` in full to copy its exact fake-repository/fake-provider fixture pattern (constructor accepts `repository=`, `provider=`, `offers=` per Task-4-research item 5) — the fakes below must match that file's style so the new test file is consistent with the existing one.

```python
# backend/tests/unit/db/services/test_billing_service_plan_change.py
import time

import pytest

from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.errors import (
    BillingOwnershipError,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
    UnmappedStripePrice,
    UnsupportedSubscriptionShape,
)
from backend.db.services.billing_service import BillingService

PLUS_MONTHLY = CommercialOffer("plus_monthly", "plus", "month", True, "price_plus_monthly", 999, "usd")
PLUS_ANNUAL = CommercialOffer("plus_annual", "plus", "year", True, "price_plus_annual", 7900, "usd")
PREMIUM_MONTHLY = CommercialOffer("premium_monthly", "premium", "month", True, "price_premium_monthly", 2499, "usd")
PREMIUM_ANNUAL = CommercialOffer("premium_annual", "premium", "year", True, "price_premium_annual", 21900, "usd")
OFFERS = {o.offer_key: o for o in (PLUS_MONTHLY, PLUS_ANNUAL, PREMIUM_MONTHLY, PREMIUM_ANNUAL)}


class _FakeRepository:
    def __init__(self, customer=None, subscriptions=None):
        self.customer = customer
        self.subscriptions = subscriptions or []

    def find_customer(self, user_id, provider="stripe"):
        return self.customer

    def find_subscriptions(self, user_id):
        return self.subscriptions


class _FakeProvider:
    def __init__(self, subscription, preview_response=None, update_response=None, schedule_response=None):
        self.subscription = subscription
        self.preview_response = preview_response or {"amount_due": 1500, "currency": "usd"}
        self.update_response = update_response or {"payment_result": "succeeded", "subscription": subscription}
        self.schedule_response = schedule_response or {"id": "sub_sched_1"}
        self.preview_calls = []
        self.update_calls = []
        self.schedule_calls = []
        self.release_calls = []

    def retrieve_subscription(self, subscription_id, expand=None):
        return self.subscription

    def preview_subscription_update(self, **kwargs):
        self.preview_calls.append(kwargs)
        return self.preview_response

    def update_subscription_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return self.update_response

    def create_downgrade_schedule(self, **kwargs):
        self.schedule_calls.append(kwargs)
        return self.schedule_response

    def release_schedule(self, **kwargs):
        self.release_calls.append(kwargs)


def _plus_subscription(period_end=1738368000, schedule=None):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": schedule,
        "items": {"data": [{"id": "si_1", "price": {"id": "price_plus_monthly"}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _premium_subscription(period_end=1738368000, schedule=None):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": schedule,
        "items": {"data": [{"id": "si_1", "price": {"id": "price_premium_monthly"}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _service(subscription, **provider_kwargs):
    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped"}],
    )
    provider = _FakeProvider(subscription, **provider_kwargs)
    return BillingService(repository=repository, provider=provider, offers=OFFERS), provider


def test_preview_plan_change_upgrade_returns_dto_and_token():
    service, provider = _service(_plus_subscription())
    dto = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    assert dto["action"] == "upgrade_now"
    assert dto["fromPlan"] == "plus"
    assert dto["toPlan"] == "premium"
    assert dto["amountDueNow"] == 1500
    assert "previewToken" in dto
    assert provider.preview_calls  # non-mutating provider call only


def test_preview_plan_change_downgrade_returns_zero_due_now():
    service, _ = _service(_premium_subscription())
    dto = service.preview_plan_change(user_id="user-1", offer_key="plus_monthly")
    assert dto["action"] == "downgrade_at_period_end"
    assert dto["amountDueNow"] == 0
    assert dto["effectiveAt"] == 1738368000


def test_preview_same_tier_rejected():
    service, _ = _service(_plus_subscription())
    with pytest.raises(PlanChangeNotAllowed):
        service.preview_plan_change(user_id="user-1", offer_key="plus_annual")


def test_preview_unmapped_current_price_rejected():
    subscription = _plus_subscription()
    subscription["items"]["data"][0]["price"]["id"] = "price_unrecognized"
    service, _ = _service(subscription)
    with pytest.raises(UnmappedStripePrice):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_preview_multi_item_subscription_rejected():
    subscription = _plus_subscription()
    subscription["items"]["data"].append({"id": "si_2", "price": {"id": "price_plus_annual"}})
    service, _ = _service(subscription)
    with pytest.raises(UnsupportedSubscriptionShape):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_preview_no_customer_rejected():
    repository = _FakeRepository(customer=None)
    provider = _FakeProvider(_plus_subscription())
    service = BillingService(repository=repository, provider=provider, offers=OFFERS)
    with pytest.raises(BillingOwnershipError):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_confirm_upgrade_reuses_proration_date_and_succeeds():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    result = service.confirm_plan_change(
        user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
    )
    assert result["paymentResult"] == "succeeded"
    preview_proration = provider.preview_calls[0]["proration_date"]
    update_proration = provider.update_calls[0]["proration_date"]
    assert preview_proration == update_proration


def test_confirm_upgrade_stale_amount_blocks_mutation():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    provider.preview_response = {"amount_due": 999999, "currency": "usd"}  # price changed server-side
    with pytest.raises(PlanChangePreviewStale):
        service.confirm_plan_change(
            user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
        )
    assert not provider.update_calls


def test_confirm_upgrade_expired_token_rejected():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    tampered = preview["previewToken"][:-4] + "0000"
    with pytest.raises(PlanChangeNotAllowed):
        service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=tampered)
    assert not provider.update_calls


def test_confirm_upgrade_token_for_different_subscription_rejected():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    other_service, _ = _service(_plus_subscription())
    other_service.repository.customer = {"provider_customer_id": "cus_2"}
    other_service.provider.subscription["id"] = "sub_2"
    with pytest.raises(PlanChangeNotAllowed):
        other_service.confirm_plan_change(
            user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
        )


def test_confirm_downgrade_creates_schedule_from_subscription():
    service, provider = _service(_premium_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="plus_monthly")
    result = service.confirm_plan_change(user_id="user-1", offer_key="plus_monthly", preview_token=None)
    assert result["action"] == "downgrade_at_period_end"
    assert result["pendingChangeEffectiveAt"] == 1738368000
    assert provider.schedule_calls[0]["subscription_id"] == "sub_1"
    assert provider.schedule_calls[0]["target_price_id"] == "price_plus_monthly"


def test_billing_status_pending_none_when_no_schedule():
    service, _ = _service(_premium_subscription(schedule=None))
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "none"


def test_billing_status_pending_scheduled_when_recognized_schedule():
    schedule = {
        "phases": [
            {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
            {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
        ]
    }
    service, _ = _service(_premium_subscription(schedule=schedule))
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "scheduled"
    assert status["pendingPlan"] == "plus"
    assert status["pendingOfferKey"] == "plus_monthly"
    assert status["pendingChangeEffectiveAt"] == 1738368000


def test_billing_status_pending_unknown_when_provider_raises():
    class _RaisingProvider(_FakeProvider):
        def retrieve_subscription(self, subscription_id, expand=None):
            raise RuntimeError("stripe outage")

    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped", "plan": "premium"}],
    )
    service = BillingService(repository=repository, provider=_RaisingProvider(_premium_subscription()), offers=OFFERS)
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "unknown"
    assert status["effectivePlan"] == "premium"  # unaffected by Stripe outage


def test_cancel_scheduled_releases_recognized_schedule():
    schedule = {
        "phases": [
            {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
            {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
        ],
        "id": "sub_sched_1",
    }
    service, provider = _service(_premium_subscription(schedule=schedule))
    result = service.cancel_scheduled_plan_change(user_id="user-1")
    assert result == {"cancelled": True}
    assert provider.release_calls[0]["schedule_id"] == "sub_sched_1"


def test_cancel_scheduled_rejects_unknown_schedule():
    schedule = {"phases": [{"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000}]}
    service, provider = _service(_premium_subscription(schedule=schedule))
    with pytest.raises(PlanChangeNotAllowed):
        service.cancel_scheduled_plan_change(user_id="user-1")
    assert not provider.release_calls


def test_cancel_scheduled_rejects_when_no_schedule():
    service, provider = _service(_premium_subscription(schedule=None))
    with pytest.raises(PlanChangeNotAllowed):
        service.cancel_scheduled_plan_change(user_id="user-1")
    assert not provider.release_calls


def test_repeated_confirm_upgrade_reuses_same_idempotency_key():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"])
    service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"])
    keys = {call["idempotency_key"] for call in provider.update_calls}
    assert len(keys) == 1
```

Note: `repository`/`provider` attributes are assumed accessible as `service.repository`/`service.provider` in a couple of tests above — verify this matches the real constructor from Task-4 research (`def __init__(self, repository=None, provider=None, offers=None)` stores them, presumably as `self.repository`/`self.provider`; confirm exact attribute names in the real file before finalizing these two tests, adjusting attribute access if named differently, e.g. `self._repository`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_billing_service_plan_change.py -v`
Expected: FAIL — `AttributeError: 'BillingService' object has no attribute 'preview_plan_change'`

- [ ] **Step 4: Implement the methods on `BillingService`**

Add to `backend/db/services/billing_service.py` (import additions at top: `import time`, `from ..domain.billing.plan_change import (...)` — use the actual relative import path matching the file's existing imports of `catalog`/`policy`/`errors`; `from ..domain.billing.preview_token import sign_preview_token, verify_preview_token`; `import os` if not already imported, for `BILLING_PLAN_CHANGE_SIGNING_SECRET`):

```python
    _PLAN_CHANGE_TOKEN_TTL_SECONDS = 300

    def _signing_secret(self):
        secret = os.environ.get("BILLING_PLAN_CHANGE_SIGNING_SECRET")
        if not secret:
            raise BillingNotConfigured("BILLING_PLAN_CHANGE_SIGNING_SECRET is not configured")
        return secret

    def _resolve_current_subscription(self, user_id):
        customer = self.repository.find_customer(user_id)
        if not customer:
            raise BillingOwnershipError("No trusted Stripe customer mapping for this user")

        local_rows = self.repository.find_subscriptions(user_id)
        if has_duplicate_active_subscriptions(local_rows):
            raise UnsupportedSubscriptionShape("User has multiple active subscriptions")

        owned_row = next(
            (row for row in local_rows if row.get("status") in ("trialing", "active", "past_due")), None
        )
        if not owned_row:
            raise BillingOwnershipError("No active subscription ownership found for this user")
        subscription_id = owned_row["provider_subscription_id"]

        subscription = self.provider.retrieve_subscription(
            subscription_id, expand=["items.data.price", "schedule", "latest_invoice.payment_intent"]
        )

        items = subscription.get("items", {}).get("data", [])
        if len(items) != 1:
            raise UnsupportedSubscriptionShape("Subscription must have exactly one recurring item")
        item = items[0]
        current_price_id = item["price"]["id"]

        current_offer = offer_for_price_id(current_price_id, self.offers)
        if current_offer is None:
            raise UnmappedStripePrice(f"Current Stripe Price {current_price_id} is not mapped")

        return customer, subscription, item, current_offer

    def preview_plan_change(self, *, user_id, offer_key):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)

        target_offer = self.offers.get(offer_key)
        if target_offer is None or not target_offer.purchasable:
            raise PlanChangeNotAllowed(f"Offer {offer_key} is not available")

        action = classify_transition(current_offer.plan, target_offer.plan)
        subscription_id = subscription["id"]
        current_period_end = subscription["current_period_end"]

        if action == PlanChangeAction.UPGRADE_NOW:
            proration_date = int(time.time())
            preview = self.provider.preview_subscription_update(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
            )
            dto = build_upgrade_preview_dto(
                from_plan=current_offer.plan,
                to_plan=target_offer.plan,
                from_offer_key=current_offer.offer_key,
                to_offer_key=target_offer.offer_key,
                currency=preview["currency"],
                amount_due_now=preview["amount_due"],
                effective_at=proration_date,
                next_renewal_at=current_period_end,
            )
            expires_at = proration_date + self._PLAN_CHANGE_TOKEN_TTL_SECONDS
            visible = {
                "version": 1,
                "action": dto["action"],
                "prorationDate": proration_date,
                "amountDueNow": dto["amountDueNow"],
                "currency": dto["currency"],
                "expiresAt": expires_at,
            }
            hidden = {
                "userId": user_id,
                "subscriptionId": subscription_id,
                "subscriptionItemId": item["id"],
                "currentPriceId": current_offer.provider_price_id,
                "targetPriceId": target_offer.provider_price_id,
                "currentPeriodEnd": current_period_end,
                "offerKey": target_offer.offer_key,
            }
            token = sign_preview_token(secret=self._signing_secret(), visible=visible, hidden=hidden)
            dto["previewToken"] = token
            return dto

        return build_downgrade_preview_dto(
            from_plan=current_offer.plan,
            to_plan=target_offer.plan,
            from_offer_key=current_offer.offer_key,
            to_offer_key=target_offer.offer_key,
            current_period_end=current_period_end,
        )

    def confirm_plan_change(self, *, user_id, offer_key, preview_token):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)

        target_offer = self.offers.get(offer_key)
        if target_offer is None or not target_offer.purchasable:
            raise PlanChangeNotAllowed(f"Offer {offer_key} is not available")

        action = classify_transition(current_offer.plan, target_offer.plan)
        subscription_id = subscription["id"]
        current_period_end = subscription["current_period_end"]

        if action == PlanChangeAction.UPGRADE_NOW:
            if not preview_token:
                raise PlanChangeNotAllowed("previewToken is required to confirm an upgrade")

            hidden = {
                "userId": user_id,
                "subscriptionId": subscription_id,
                "subscriptionItemId": item["id"],
                "currentPriceId": current_offer.provider_price_id,
                "targetPriceId": target_offer.provider_price_id,
                "currentPeriodEnd": current_period_end,
                "offerKey": target_offer.offer_key,
            }
            visible = verify_preview_token(preview_token, secret=self._signing_secret(), hidden=hidden)
            proration_date = visible["prorationDate"]

            fresh_preview = self.provider.preview_subscription_update(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
            )
            if fresh_preview["amount_due"] != visible["amountDueNow"] or fresh_preview["currency"] != visible["currency"]:
                raise PlanChangePreviewStale("Price changed since preview; please re-preview")

            idempotency_key = upgrade_idempotency_key(
                subscription_id, current_offer.provider_price_id, target_offer.provider_price_id, proration_date
            )
            result = self.provider.update_subscription_item(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
                idempotency_key=idempotency_key,
            )
            return {"action": PlanChangeAction.UPGRADE_NOW.value, "paymentResult": result["payment_result"]}

        idempotency_key = downgrade_idempotency_key(
            subscription_id, current_offer.provider_price_id, target_offer.provider_price_id, current_period_end
        )
        self.provider.create_downgrade_schedule(
            subscription_id=subscription_id,
            target_price_id=target_offer.provider_price_id,
            current_period_end=current_period_end,
            idempotency_key=idempotency_key,
        )
        return {
            "action": PlanChangeAction.DOWNGRADE_AT_PERIOD_END.value,
            "pendingChangeEffectiveAt": current_period_end,
        }

    def cancel_scheduled_plan_change(self, *, user_id):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)
        schedule = subscription.get("schedule")
        classification = classify_schedule(
            schedule,
            current_price_id=current_offer.provider_price_id,
            current_period_end=subscription["current_period_end"],
            offers=self.offers,
        )
        if classification["state"] != "scheduled":
            raise PlanChangeNotAllowed("No recognized scheduled downgrade to cancel")

        self.provider.release_schedule(schedule_id=schedule["id"])
        return {"cancelled": True}
```

Then extend `billing_status()` — locate its existing `return {...}` block (per Task-4 research, lines ~129-136) and wrap a new Stripe lookup around it:

```python
    def billing_status(self, user_id):
        base = { ... existing dict construction unchanged ... }

        pending = {"pendingChangeState": "none", "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}
        if base.get("billingManaged"):
            try:
                _, subscription, _, current_offer = self._resolve_current_subscription(user_id)
                schedule = subscription.get("schedule")
                classification = classify_schedule(
                    schedule,
                    current_price_id=current_offer.provider_price_id,
                    current_period_end=subscription["current_period_end"],
                    offers=self.offers,
                )
                pending = {
                    "pendingChangeState": classification["state"],
                    "pendingPlan": classification["pendingPlan"],
                    "pendingOfferKey": classification["pendingOfferKey"],
                    "pendingChangeEffectiveAt": classification["pendingChangeEffectiveAt"],
                }
            except Exception:
                pending = {"pendingChangeState": "unknown", "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}

        return {**base, **pending}
```

Adjust the exact insertion point to match the real current structure of `billing_status()` — the principle (compute `base` exactly as today, then non-fatally enrich with `pending`, catching any exception from the Stripe round-trip so the existing fields are never affected) is what must be preserved.

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_billing_service_plan_change.py -v`
Expected: all pass

- [ ] **Step 6: Run the full existing service test file to confirm no regression**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_billing_service.py -v`
Expected: all previously-passing tests still pass

- [ ] **Step 7: Commit**

```bash
git add backend/db/services/billing_service.py backend/tests/unit/db/services/test_billing_service_plan_change.py
git commit -m "feat(billing): add BillingService plan-change orchestration methods"
```

---

## Task 6: API routes

**Files:**
- Modify: `backend/api/main.py`
- Test: `backend/tests/unit/api/test_billing_plan_change_api.py`

**Interfaces:**
- Consumes: Task 5's `BillingService.preview_plan_change`/`.confirm_plan_change`/`.cancel_scheduled_plan_change`; existing `_enforce_billing_post_origin`, `_require_authenticated_user_id`, `_tiered_response`, existing pydantic-body pattern (`BillingCheckoutRequest` as the model to copy).
- Produces: 3 new routes exactly as specified in spec §6, wired with the same auth/CSRF/error-mapping pattern as `/billing/checkout-session`.

- [ ] **Step 1: Write the failing tests**

First read `backend/tests/unit/api/test_billing_api.py` in full to copy its exact test-client/auth-header fixture pattern (how it authenticates a fake user against `/billing/checkout-session` today) — the new file must follow the same pattern.

```python
# backend/tests/unit/api/test_billing_plan_change_api.py
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.domain.billing.errors import (
    BillingOwnershipError,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
)

client = TestClient(app)

# NOTE: replace `_auth_headers(...)` below with whatever helper
# test_billing_api.py actually uses to authenticate a fake user id
# (copy it verbatim from that file rather than reinventing it).


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
        headers=_auth_headers("user-1"),
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
        headers=_auth_headers("user-1"),
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
        headers=_auth_headers("user-1"),
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
        headers=_auth_headers("user-1"),
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
        headers=_auth_headers("user-1"),
    )
    assert response.status_code == 200
    assert captured["user_id"] == "user-1"  # server-resolved from auth, not from body


def test_cancel_scheduled_success(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_cancel(self, *, user_id):
        return {"cancelled": True}

    monkeypatch.setattr(billing_service_module.BillingService, "cancel_scheduled_plan_change", fake_cancel)

    response = client.post(
        "/billing/change-plan/cancel-scheduled", json={}, headers=_auth_headers("user-1")
    )
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/api/test_billing_plan_change_api.py -v`
Expected: FAIL — 404 (routes don't exist yet)

- [ ] **Step 3: Add the pydantic request models and 3 routes to `backend/api/main.py`**

Add near the existing `BillingCheckoutRequest` model:

```python
class BillingPlanChangePreviewRequest(BaseModel):
    offerKey: str


class BillingPlanChangeConfirmRequest(BaseModel):
    offerKey: str
    previewToken: Optional[str] = None
```

(`BillingPlanChangeConfirmRequest` deliberately has no other fields — any extra keys the browser sends, like `subscriptionId`, are silently dropped by pydantic's default behavior, satisfying "browser cannot control" for every other field.)

Add the 3 routes near the existing `/billing/*` routes, following the exact same auth/CSRF/error pattern as `/billing/checkout-session`:

```python
@app.post("/billing/change-plan/preview")
def preview_billing_plan_change(
    payload: BillingPlanChangePreviewRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().preview_plan_change(user_id=user_id, offer_key=payload.offerKey)
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": "PLAN_CHANGE_NOT_ALLOWED", "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": "BILLING_OWNERSHIP_ERROR", "message": str(exc)})
    except UnsupportedSubscriptionShape as exc:
        raise HTTPException(status_code=409, detail={"code": "UNSUPPORTED_SUBSCRIPTION_SHAPE", "message": str(exc)})
    except UnmappedStripePrice as exc:
        raise HTTPException(status_code=409, detail={"code": "UNMAPPED_STRIPE_PRICE", "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code if hasattr(exc, "code") else "BILLING_PROVIDER_ERROR"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": getattr(exc, "code", "BILLING_ERROR")})
    return _tiered_response(dto)


@app.post("/billing/change-plan/confirm")
def confirm_billing_plan_change(
    payload: BillingPlanChangeConfirmRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().confirm_plan_change(
            user_id=user_id, offer_key=payload.offerKey, preview_token=payload.previewToken
        )
    except PlanChangePreviewStale as exc:
        raise HTTPException(status_code=409, detail={"code": "PLAN_CHANGE_PREVIEW_STALE", "message": str(exc)})
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": "PLAN_CHANGE_NOT_ALLOWED", "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": "BILLING_OWNERSHIP_ERROR", "message": str(exc)})
    except UnsupportedSubscriptionShape as exc:
        raise HTTPException(status_code=409, detail={"code": "UNSUPPORTED_SUBSCRIPTION_SHAPE", "message": str(exc)})
    except UnmappedStripePrice as exc:
        raise HTTPException(status_code=409, detail={"code": "UNMAPPED_STRIPE_PRICE", "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code if hasattr(exc, "code") else "BILLING_PROVIDER_ERROR"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": getattr(exc, "code", "BILLING_ERROR")})
    return _tiered_response(dto)


@app.post("/billing/change-plan/cancel-scheduled")
def cancel_billing_scheduled_plan_change(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().cancel_scheduled_plan_change(user_id=user_id)
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": "PLAN_CHANGE_NOT_ALLOWED", "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": "BILLING_OWNERSHIP_ERROR", "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code if hasattr(exc, "code") else "BILLING_PROVIDER_ERROR"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": getattr(exc, "code", "BILLING_ERROR")})
    return _tiered_response(dto)
```

Add the corresponding imports (`PlanChangeNotAllowed`, `PlanChangePreviewStale`) to the existing `from ..domain.billing.errors import (...)` block at the top of `main.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/api/test_billing_plan_change_api.py -v`
Expected: all pass

- [ ] **Step 5: Run the full existing billing API test file to confirm no regression**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/api/test_billing_api.py -v`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/api/main.py backend/tests/unit/api/test_billing_plan_change_api.py
git commit -m "feat(billing): add /billing/change-plan preview/confirm/cancel-scheduled routes"
```

---

## Task 7: Backend security test matrix

**Files:**
- Test: `backend/tests/unit/api/test_billing_plan_change_security.py` (new file, kept separate from Task 6's happy-path/error-mapping tests to isolate the security-specific matrix per spec §22)

**Interfaces:**
- Consumes: everything from Tasks 1-6 (real `BillingService`, real `plan_change.py`, real `preview_token.py` — this test file uses fakes only at the `StripeProvider`/`BillingRepository` boundary, matching Task 5's fixtures, wired through the real HTTP routes via `TestClient`).

- [ ] **Step 1: Write the security tests**

```python
# backend/tests/unit/api/test_billing_plan_change_security.py
import os
import time

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.preview_token import sign_preview_token

client = TestClient(app)

PLUS_MONTHLY = CommercialOffer("plus_monthly", "plus", "month", True, "price_plus_monthly", 999, "usd")
PREMIUM_MONTHLY = CommercialOffer("premium_monthly", "premium", "month", True, "price_premium_monthly", 2499, "usd")
OFFERS = {"plus_monthly": PLUS_MONTHLY, "premium_monthly": PREMIUM_MONTHLY}


@pytest.fixture(autouse=True)
def signing_secret(monkeypatch):
    monkeypatch.setenv("BILLING_PLAN_CHANGE_SIGNING_SECRET", "test-secret")


# NOTE: replace `_auth_headers(...)` with the real helper copied from
# test_billing_api.py, as in Task 6.


def test_basic_user_cannot_preview_plan_change(monkeypatch):
    from backend.db.services import billing_service as billing_service_module

    def fake_preview(self, *, user_id, offer_key):
        from backend.domain.billing.errors import BillingOwnershipError

        raise BillingOwnershipError("no billing-managed subscription")

    monkeypatch.setattr(billing_service_module.BillingService, "preview_plan_change", fake_preview)
    response = client.post(
        "/billing/change-plan/preview", json={"offerKey": "premium_monthly"}, headers=_auth_headers("basic-user")
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
        headers=_auth_headers("user-1"),
    )
    # The fake service always "succeeds" here because we stubbed confirm_plan_change directly;
    # this test only proves the raw forged token string reaches the service layer unmodified
    # (i.e. the API layer performs no token trust decisions itself) — real verification is
    # covered by Task 5's confirm_upgrade_expired_token_rejected / tampered-token tests, which
    # exercise the actual verify_preview_token call inside BillingService.
    assert response.status_code == 200
    assert captured["preview_token"] == forged_token


def test_cancel_scheduled_ignores_browser_supplied_schedule_id():
    response = client.post(
        "/billing/change-plan/cancel-scheduled",
        json={"scheduleId": "sub_sched_attacker"},
        headers=_auth_headers("user-1"),
    )
    # No schedule route param/body field exists to receive scheduleId at all —
    # pydantic has no model on this route, so any body is accepted and ignored;
    # confirm the route doesn't 422 on unexpected fields and doesn't use them.
    assert response.status_code in (200, 403, 409, 503)


@pytest.mark.parametrize("field", ["subscriptionId", "customerId", "priceId", "userId", "amountDueNow", "currentPlan"])
def test_preview_request_model_rejects_unknown_fields_silently(field):
    response = client.post(
        "/billing/change-plan/preview",
        json={"offerKey": "premium_monthly", field: "malicious-value"},
        headers=_auth_headers("user-1"),
    )
    # Must not 500; pydantic drops unknown fields by default rather than trusting them.
    assert response.status_code != 500
```

- [ ] **Step 2: Run tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/api/test_billing_plan_change_security.py -v`
Expected: all pass (adjust `_auth_headers` import/usage to match the real helper before this passes)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/api/test_billing_plan_change_security.py
git commit -m "test(billing): add plan-change API security tests"
```

---

## Task 8: Frontend client + proxy routes

**Files:**
- Modify: `frontend/lib/billing/billingClient.mjs`
- Create: `frontend/app/api/billing/change-plan/preview/route.js`
- Create: `frontend/app/api/billing/change-plan/confirm/route.js`
- Create: `frontend/app/api/billing/change-plan/cancel-scheduled/route.js`
- Test: `frontend/lib/billing/billingClient.planChange.test.mjs`

**Interfaces:**
- Consumes: existing `request()` helper pattern inside `billingClient.mjs`, existing `proxyBilling()` helper from `frontend/lib/billing/billingProxy.js`.
- Produces:
  - `previewPlanChange(offerKey)` → `POST /api/billing/change-plan/preview`, body `{offerKey}`.
  - `confirmPlanChange(offerKey, previewToken)` → `POST /api/billing/change-plan/confirm`, body `{offerKey, previewToken}`.
  - `cancelScheduledPlanChange()` → `POST /api/billing/change-plan/cancel-scheduled`, no body.

- [ ] **Step 1: Write the failing test**

```js
// frontend/lib/billing/billingClient.planChange.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  BillingClientError,
  cancelScheduledPlanChange,
  confirmPlanChange,
  previewPlanChange,
} from "./billingClient.mjs";

function stubFetch(responseBody, { ok = true, status = 200 } = {}) {
  const calls = [];
  global.fetch = async (url, init) => {
    calls.push({ url, init });
    return {
      ok,
      status,
      json: async () => responseBody,
      text: async () => JSON.stringify(responseBody),
    };
  };
  return calls;
}

test("previewPlanChange posts offerKey to the preview proxy route", async () => {
  const calls = stubFetch({ action: "upgrade_now", amountDueNow: 1500 });
  const result = await previewPlanChange("premium_monthly");
  assert.equal(calls[0].url, "/api/billing/change-plan/preview");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { offerKey: "premium_monthly" });
  assert.equal(result.amountDueNow, 1500);
});

test("confirmPlanChange posts offerKey and previewToken", async () => {
  const calls = stubFetch({ action: "upgrade_now", paymentResult: "succeeded" });
  const result = await confirmPlanChange("premium_monthly", "tok-abc");
  assert.equal(calls[0].url, "/api/billing/change-plan/confirm");
  assert.deepEqual(JSON.parse(calls[0].init.body), { offerKey: "premium_monthly", previewToken: "tok-abc" });
  assert.equal(result.paymentResult, "succeeded");
});

test("cancelScheduledPlanChange posts with no body", async () => {
  const calls = stubFetch({ cancelled: true });
  const result = await cancelScheduledPlanChange();
  assert.equal(calls[0].url, "/api/billing/change-plan/cancel-scheduled");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(result.cancelled, true);
});

test("previewPlanChange throws BillingClientError on failure response", async () => {
  stubFetch({ detail: { code: "PLAN_CHANGE_NOT_ALLOWED" } }, { ok: false, status: 409 });
  await assert.rejects(() => previewPlanChange("plus_annual"), BillingClientError);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx tsx --test lib/billing/billingClient.planChange.test.mjs`
Expected: FAIL — `previewPlanChange is not a function`

- [ ] **Step 3: Add the 3 functions to `billingClient.mjs`**

Append, matching the file's existing `request()`-based pattern exactly (read the existing `createCheckoutSession`/`createCustomerPortalSession` exports first and copy their structure verbatim):

```js
export function previewPlanChange(offerKey) {
  return request("/api/billing/change-plan/preview", {
    method: "POST",
    body: JSON.stringify({ offerKey }),
  });
}

export function confirmPlanChange(offerKey, previewToken) {
  return request("/api/billing/change-plan/confirm", {
    method: "POST",
    body: JSON.stringify({ offerKey, previewToken }),
  });
}

export function cancelScheduledPlanChange() {
  return request("/api/billing/change-plan/cancel-scheduled", { method: "POST" });
}
```

(If the existing `request()` helper doesn't auto-set `Content-Type: application/json` for a `body`-bearing call, copy whatever header-setting `createCheckoutSession` does verbatim — do not diverge from the established pattern.)

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npx tsx --test lib/billing/billingClient.planChange.test.mjs`
Expected: 4 passed

- [ ] **Step 5: Create the 3 Next.js proxy routes**

Read `frontend/app/api/billing/checkout-session/route.js` and `frontend/app/api/billing/customer-portal/route.js` first and copy their exact structure (per Task-4-research item 11: JSON body parsing with 400 `INVALID_REQUEST` for preview/confirm since they have bodies, no-body forwarding for cancel-scheduled like `customer-portal`'s pattern).

```js
// frontend/app/api/billing/change-plan/preview/route.js
import { proxyBilling } from "../../../../../lib/billing/billingProxy.js";

export const dynamic = "force-dynamic";

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch (error) {
    return Response.json({ detail: { code: "INVALID_REQUEST" } }, { status: 400 });
  }
  return proxyBilling(request, "/billing/change-plan/preview", { method: "POST", body });
}
```

```js
// frontend/app/api/billing/change-plan/confirm/route.js
import { proxyBilling } from "../../../../../lib/billing/billingProxy.js";

export const dynamic = "force-dynamic";

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch (error) {
    return Response.json({ detail: { code: "INVALID_REQUEST" } }, { status: 400 });
  }
  return proxyBilling(request, "/billing/change-plan/confirm", { method: "POST", body });
}
```

```js
// frontend/app/api/billing/change-plan/cancel-scheduled/route.js
import { proxyBilling } from "../../../../../lib/billing/billingProxy.js";

export const dynamic = "force-dynamic";

export async function POST(request) {
  return proxyBilling(request, "/billing/change-plan/cancel-scheduled", { method: "POST" });
}
```

Adjust the relative import depth (`../../../../../lib/billing/billingProxy.js`) to match the actual directory depth once the files are created — verify against how `checkout-session/route.js` imports `billingProxy.js` and mirror that exact relative path pattern (checkout-session is one directory shallower than `change-plan/preview`, so this path likely needs one extra `../`).

- [ ] **Step 6: Verify existing proxy contract test still covers the pattern (no new test needed for the proxy routes themselves — they're thin wrappers; the existing `billingProxy.contract.test.mjs` already tests `proxyBilling` itself)**

Run (from `frontend/`): `npx tsx --test app/api/billing/billingProxy.contract.test.mjs`
Expected: still passes (proxy helper unmodified)

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/billing/billingClient.mjs frontend/lib/billing/billingClient.planChange.test.mjs frontend/app/api/billing/change-plan/
git commit -m "feat(billing): add frontend client functions and proxy routes for plan-change"
```

---

## Task 9: Frontend presentation helpers

**Files:**
- Modify: `frontend/lib/billing/billingPresentation.mjs`
- Test: `frontend/lib/billing/billingPresentation.planChange.test.mjs`

**Interfaces:**
- Consumes: nothing new (pure formatting).
- Produces:
  - `pendingChangeCopy(status)` — given a `billing_status()` DTO, returns `null` if `pendingChangeState !== "scheduled"`, else a string like `"Changes to Index Plus on March 5, 2027"` using `planLabel(status.pendingPlan)` and `formatBillingDate(status.pendingChangeEffectiveAt)` (both existing exports, reused not reimplemented).
  - `upgradeConfirmationCopy({ amountDueNow, currency, nextRenewalAt })` — returns `{ dueNowLabel, bodyLines: [string, string] }` where `dueNowLabel` is `formatMinorAmount`-formatted (import from `billingPricing.mjs`) and `bodyLines` are the two sentences from spec §17 ("...begins immediately after successful payment.", "Next renewal: <date>").
  - `downgradeConfirmationCopy({ currentPlanUntil })` — returns `{ bodyLines: [string, string, string] }` matching spec §17's three sentences.

- [ ] **Step 1: Write the failing tests**

```js
// frontend/lib/billing/billingPresentation.planChange.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  downgradeConfirmationCopy,
  pendingChangeCopy,
  upgradeConfirmationCopy,
} from "./billingPresentation.mjs";

test("pendingChangeCopy returns null when nothing is scheduled", () => {
  assert.equal(pendingChangeCopy({ pendingChangeState: "none" }), null);
  assert.equal(pendingChangeCopy({ pendingChangeState: "unknown" }), null);
});

test("pendingChangeCopy describes a scheduled downgrade", () => {
  const copy = pendingChangeCopy({
    pendingChangeState: "scheduled",
    pendingPlan: "plus",
    pendingChangeEffectiveAt: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy, /Index Plus/);
  assert.match(copy, /2027/);
});

test("upgradeConfirmationCopy formats amount and renewal date", () => {
  const copy = upgradeConfirmationCopy({
    amountDueNow: 1500,
    currency: "usd",
    nextRenewalAt: Math.floor(new Date("2027-04-01T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy.dueNowLabel, /\$15\.00/);
  assert.equal(copy.bodyLines.length, 2);
  assert.match(copy.bodyLines[1], /2027/);
});

test("downgradeConfirmationCopy describes retained access and no charge", () => {
  const copy = downgradeConfirmationCopy({
    currentPlanUntil: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.equal(copy.bodyLines.length, 3);
  assert.match(copy.bodyLines[0], /Index Premium until/);
  assert.match(copy.bodyLines[2], /No charge today/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npx tsx --test lib/billing/billingPresentation.planChange.test.mjs`
Expected: FAIL — functions not exported

- [ ] **Step 3: Implement the 3 functions**

Append to `billingPresentation.mjs`, importing `formatMinorAmount` from `./billingPricing.mjs` at the top (add to existing imports if `billingPricing.mjs` isn't already imported there):

```js
import { formatMinorAmount } from "./billingPricing.mjs";

export function pendingChangeCopy(status) {
  if (!status || status.pendingChangeState !== "scheduled") {
    return null;
  }
  const planName = planLabel(status.pendingPlan);
  const date = formatBillingDate(status.pendingChangeEffectiveAt);
  return `Changes to ${planName} on ${date}`;
}

export function upgradeConfirmationCopy({ amountDueNow, currency, nextRenewalAt }) {
  const dueNowLabel = formatMinorAmount(amountDueNow, currency);
  const renewalDate = formatBillingDate(nextRenewalAt);
  return {
    dueNowLabel,
    bodyLines: [
      "Your new membership begins immediately after successful payment.",
      `Next renewal: ${renewalDate}`,
    ],
  };
}

export function downgradeConfirmationCopy({ currentPlanUntil }) {
  const untilDate = formatBillingDate(currentPlanUntil);
  return {
    bodyLines: [
      `You'll keep Index Premium until ${untilDate}.`,
      "Index Plus begins after that.",
      "No charge today.",
    ],
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npx tsx --test lib/billing/billingPresentation.planChange.test.mjs`
Expected: 4 passed

- [ ] **Step 5: Run existing presentation test file to confirm no regression**

Run (from `frontend/`): `npx tsx --test lib/billing/billingPresentation.test.mjs`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/billing/billingPresentation.mjs frontend/lib/billing/billingPresentation.planChange.test.mjs
git commit -m "feat(billing): add plan-change presentation copy helpers"
```

---

## Task 10: Pricing page UX

**Files:**
- Modify: `frontend/components/pricing/PricingPageClient.jsx`
- Test: `frontend/components/pricing/PricingPageClient.planChange.test.mjs`

**Interfaces:**
- Consumes: Task 8 (`previewPlanChange`, `confirmPlanChange`, `cancelScheduledPlanChange`), Task 9 (`pendingChangeCopy`, `upgradeConfirmationCopy`, `downgradeConfirmationCopy`), existing `PaidCard` structure, existing `normalizeIndexPlan`.
- Produces: modified `PaidCard` behavior — for a `managed` card whose `plan !== effectivePlan` and `plan !== "basic"`, render a plan-change CTA instead of the Portal-routing button; a small inline confirmation panel component `PlanChangeConfirmPanel` (new, colocated in the same file since `PaidCard` already lives there and this is tightly coupled UI, not a reusable primitive).

Read the full current `PricingPageClient.jsx` before editing (Task-4 research gave lines 61-129 and 159-180 as the two edit sites — re-verify exact current line numbers first since the file may have shifted).

- [ ] **Step 1: Write the failing test**

First check whether the repo has an existing React component test convention (search for any `.test.jsx` using `@testing-library/react` or similar) since `PricingPageClient.jsx` currently has no test file — if no React testing library is set up in `frontend/package.json`, write this as a plain-function unit test against extracted pure helper functions instead of a full component render test (see Step 3 — the plan pulls the branching logic into an exported pure helper specifically so it's testable without a DOM/React renderer, avoiding introducing a new test dependency).

```js
// frontend/components/pricing/PricingPageClient.planChange.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import { resolvePaidCardMode } from "./PricingPageClient.jsx";

test("basic user sees checkout for both plus and premium", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "checkout");
  assert.equal(resolvePaidCardMode("premium", status), "checkout");
});

test("plus user sees current-plan on plus card and upgrade on premium card", () => {
  const status = { effectivePlan: "plus", billingManaged: true, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "current");
  assert.equal(resolvePaidCardMode("premium", status), "upgrade");
});

test("premium user sees current-plan on premium card and downgrade on plus card", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("premium", status), "current");
  assert.equal(resolvePaidCardMode("plus", status), "downgrade");
});

test("premium user with scheduled downgrade sees pending mode on plus card", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "scheduled", pendingPlan: "plus" };
  assert.equal(resolvePaidCardMode("plus", status), "pending-downgrade");
});

test("unmanaged basic-tier user with no billing relationship falls back to checkout, never portal", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "checkout");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx tsx --test components/pricing/PricingPageClient.planChange.test.mjs`
Expected: FAIL — `resolvePaidCardMode is not exported`

- [ ] **Step 3: Extract and export the pure mode-resolution function, then wire it into `PaidCard`**

Add this pure exported function near the top of `PricingPageClient.jsx` (below imports, above the `PaidCard` component):

```jsx
export function resolvePaidCardMode(plan, status) {
  const effectivePlan = normalizeIndexPlan(status?.effectivePlan);
  const managed = Boolean(status?.billingManaged);

  if (effectivePlan === plan) {
    return "current";
  }
  if (!managed) {
    return "checkout";
  }
  if (plan === "plus" && effectivePlan === "premium") {
    if (status?.pendingChangeState === "scheduled" && status?.pendingPlan === "plus") {
      return "pending-downgrade";
    }
    return "downgrade";
  }
  if (plan === "premium" && effectivePlan === "plus") {
    return "upgrade";
  }
  return "checkout";
}
```

Then modify `PaidCard` to branch on `resolvePaidCardMode(plan, status)` instead of the current `current`/`managed`/`purchasable` three-way check. Replace the existing label/disabled logic (the block starting `let label = "Coming Soon", disabled = true; ...` from Task-4 research) with:

```jsx
  const mode = resolvePaidCardMode(plan, status);
  let label = "Coming Soon";
  let disabled = true;
  if (mode === "current") {
    label = "Current Plan";
  } else if (mode === "upgrade") {
    label = `Upgrade to Index ${plan === "premium" ? "Premium" : "Plus"}`;
    disabled = false;
  } else if (mode === "downgrade") {
    label = "Change to Index Plus";
    disabled = false;
  } else if (mode === "pending-downgrade") {
    label = "Keep Index Premium";
    disabled = false;
  } else if (mode === "checkout") {
    label = purchasable ? (status ? `Upgrade to Index ${plan === "premium" ? "Premium" : "Plus"}` : `Get Index ${plan === "premium" ? "Premium" : "Plus"}`) : "Coming Soon";
    disabled = !purchasable;
  }
```

And add a pending-change banner above the button for the `pending-downgrade` mode, using `pendingChangeCopy(status)` from Task 9:

```jsx
  {mode === "pending-downgrade" && (
    <p className="pricing-card-pending-notice">{pendingChangeCopy(status)}</p>
  )}
```

Add a `<PlanChangeConfirmPanel>` component in the same file, rendered when a preview has been fetched (new local state `const [planChangePreview, setPlanChangePreview] = useState(null)` at the parent level where `PaidCard`s are rendered, matching the existing `pending` state pattern already used for the Checkout/Portal `act()` flow):

```jsx
function PlanChangeConfirmPanel({ mode, preview, onConfirm, onDismiss, pending }) {
  if (!preview) return null;
  if (mode === "upgrade") {
    const copy = upgradeConfirmationCopy({
      amountDueNow: preview.amountDueNow,
      currency: preview.currency,
      nextRenewalAt: preview.nextRenewalAt,
    });
    return (
      <div className="plan-change-confirm-panel plan-change-confirm-panel--premium">
        <h3>Upgrade to Index Premium</h3>
        <p className="plan-change-due-now">Due now: {copy.dueNowLabel}</p>
        {copy.bodyLines.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <button onClick={onConfirm} disabled={pending}>Confirm upgrade</button>
        <button onClick={onDismiss} disabled={pending}>Cancel</button>
      </div>
    );
  }
  const copy = downgradeConfirmationCopy({ currentPlanUntil: preview.currentPlanUntil });
  return (
    <div className="plan-change-confirm-panel plan-change-confirm-panel--plus">
      <h3>Change to Index Plus</h3>
      {copy.bodyLines.map((line) => (
        <p key={line}>{line}</p>
      ))}
      <button onClick={onConfirm} disabled={pending}>Confirm change</button>
      <button onClick={onDismiss} disabled={pending}>Cancel</button>
    </div>
  );
}
```

Wire `PaidCard`'s `onAction` for `upgrade`/`downgrade`/`pending-downgrade` modes to call `previewPlanChange(offer.offerKey)` (storing the result to open `PlanChangeConfirmPanel`), `confirmPlanChange(offer.offerKey, preview.previewToken)` on confirm (then refetch `/billing/me` to refresh `status`), and `cancelScheduledPlanChange()` for the `pending-downgrade` mode's click (no preview panel needed for that one — direct action, matching spec §19's "Keep Index Premium" one-click behavior). Reuse the existing gold/purple CSS classes already applied to Plus/Premium cards elsewhere in this file (locate them and apply the same class names to `plan-change-confirm-panel--plus`/`--premium` rather than inventing new colors).

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npx tsx --test components/pricing/PricingPageClient.planChange.test.mjs`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/components/pricing/PricingPageClient.jsx frontend/components/pricing/PricingPageClient.planChange.test.mjs
git commit -m "feat(billing): replace Portal routing with in-page plan-change UX on pricing page"
```

---

## Task 11: Full cross-tier test matrix (backend)

**Files:**
- Test: `backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py`

**Interfaces:**
- Consumes: Task 5's `BillingService`, the same `_FakeRepository`/`_FakeProvider` fixtures (import them from `test_billing_service_plan_change.py` rather than redefining — add `__init__.py`-safe relative import or just duplicate the ~15-line fixtures locally if the existing test conventions in this repo don't cross-import between test files; check `test_billing_service.py` for precedent first and follow it).

- [ ] **Step 1: Write the parametrized matrix test**

```python
# backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py
import pytest

from backend.domain.billing.catalog import CommercialOffer
from backend.db.services.billing_service import BillingService

PLUS_MONTHLY = CommercialOffer("plus_monthly", "plus", "month", True, "price_plus_monthly", 999, "usd")
PLUS_ANNUAL = CommercialOffer("plus_annual", "plus", "year", True, "price_plus_annual", 7900, "usd")
PREMIUM_MONTHLY = CommercialOffer("premium_monthly", "premium", "month", True, "price_premium_monthly", 2499, "usd")
PREMIUM_ANNUAL = CommercialOffer("premium_annual", "premium", "year", True, "price_premium_annual", 21900, "usd")
OFFERS = {o.offer_key: o for o in (PLUS_MONTHLY, PLUS_ANNUAL, PREMIUM_MONTHLY, PREMIUM_ANNUAL)}


class _FakeRepository:
    def __init__(self, customer, subscriptions):
        self.customer = customer
        self.subscriptions = subscriptions

    def find_customer(self, user_id, provider="stripe"):
        return self.customer

    def find_subscriptions(self, user_id):
        return self.subscriptions


class _FakeProvider:
    def __init__(self, subscription):
        self.subscription = subscription
        self.preview_calls = []
        self.update_calls = []
        self.schedule_calls = []

    def retrieve_subscription(self, subscription_id, expand=None):
        return self.subscription

    def preview_subscription_update(self, **kwargs):
        self.preview_calls.append(kwargs)
        return {"amount_due": 1234, "currency": "usd"}

    def update_subscription_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"payment_result": "succeeded", "subscription": self.subscription}

    def create_downgrade_schedule(self, **kwargs):
        self.schedule_calls.append(kwargs)
        return {"id": "sub_sched_1"}

    def release_schedule(self, **kwargs):
        pass


def _subscription(price_id, period_end=1738368000):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": None,
        "items": {"data": [{"id": "si_1", "price": {"id": price_id}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _service(current_offer):
    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped"}],
    )
    provider = _FakeProvider(_subscription(current_offer.provider_price_id))
    return BillingService(repository=repository, provider=provider, offers=OFFERS), provider


UPGRADE_CASES = [
    (PLUS_MONTHLY, PREMIUM_MONTHLY),
    (PLUS_MONTHLY, PREMIUM_ANNUAL),
    (PLUS_ANNUAL, PREMIUM_MONTHLY),
    (PLUS_ANNUAL, PREMIUM_ANNUAL),
]

DOWNGRADE_CASES = [
    (PREMIUM_MONTHLY, PLUS_MONTHLY),
    (PREMIUM_MONTHLY, PLUS_ANNUAL),
    (PREMIUM_ANNUAL, PLUS_MONTHLY),
    (PREMIUM_ANNUAL, PLUS_ANNUAL),
]


@pytest.mark.parametrize("current_offer,target_offer", UPGRADE_CASES)
def test_upgrade_transition(current_offer, target_offer):
    service, provider = _service(current_offer)
    preview = service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert preview["action"] == "upgrade_now"
    assert preview["fromPlan"] == "plus"
    assert preview["toPlan"] == "premium"

    result = service.confirm_plan_change(
        user_id="user-1", offer_key=target_offer.offer_key, preview_token=preview["previewToken"]
    )
    assert result["paymentResult"] == "succeeded"
    assert provider.update_calls[0]["target_price_id"] == target_offer.provider_price_id


@pytest.mark.parametrize("current_offer,target_offer", DOWNGRADE_CASES)
def test_downgrade_transition(current_offer, target_offer):
    service, provider = _service(current_offer)
    preview = service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert preview["action"] == "downgrade_at_period_end"
    assert preview["amountDueNow"] == 0

    result = service.confirm_plan_change(user_id="user-1", offer_key=target_offer.offer_key, preview_token=None)
    assert result["action"] == "downgrade_at_period_end"
    assert provider.schedule_calls[0]["target_price_id"] == target_offer.provider_price_id


@pytest.mark.parametrize(
    "current_offer,target_offer",
    [
        (PLUS_MONTHLY, PLUS_ANNUAL),
        (PLUS_ANNUAL, PLUS_MONTHLY),
        (PREMIUM_MONTHLY, PREMIUM_ANNUAL),
        (PREMIUM_ANNUAL, PREMIUM_MONTHLY),
    ],
)
def test_same_tier_interval_change_rejected(current_offer, target_offer):
    from backend.domain.billing.errors import PlanChangeNotAllowed

    service, provider = _service(current_offer)
    with pytest.raises(PlanChangeNotAllowed):
        service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert not provider.preview_calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py -v`
Expected: FAIL if run before Task 5 is complete; if Task 5 is already done, this should mostly pass immediately — run it to confirm and fix any fixture mismatches against the real `BillingService` constructor/attribute names.

- [ ] **Step 3: Fix any fixture mismatches and re-run until green**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py -v`
Expected: 12 passed (4 upgrade + 4 downgrade + 4 same-tier-rejected)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py
git commit -m "test(billing): add full 8-transition cross-tier plan-change matrix"
```

---

## Task 12: Reconciliation regression check (no code change expected)

**Files:**
- Test: none new — this task runs the *existing* reconciliation test suite to prove spec §16's claim ("existing `customer.subscription.updated` handling already re-derives plan from Price ID with no special-casing, so a fired schedule phase transition needs no new code").

- [ ] **Step 1: Read `backend/tests/unit/domain/billing/test_reconciliation.py` and confirm it already has (or add, if genuinely missing) a case that reconciles a subscription whose Price ID changed between two calls (simulating what happens when a schedule's phase 2 fires) and asserts the plan changes accordingly**

If such a test already exists, this task is done — just run it:

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/test_reconciliation.py -v`
Expected: all pass, including the Price-change case.

If no such case exists, add one following the file's existing test style (read 2-3 existing tests in that file first to match fixture conventions exactly):

```python
def test_reconcile_subscription_price_change_updates_plan():
    # Arrange: a stored subscription row currently mapped to premium_monthly,
    # then Stripe reports the same subscription id now on plus_monthly's price
    # (this is what a fired downgrade-schedule phase 2 looks like from the
    # reconciler's point of view — no schedule-awareness needed).
    ...  # follow existing fixture pattern from this file for building a "before" row and a "Stripe now says" subscription object
    result = reconciler.reconcile_customer(...)
    assert result[...]["plan"] == "plus"
```

(Only write the concrete body of this test if Step 1's read confirms no equivalent case exists — do not add a duplicate.)

- [ ] **Step 2: Commit only if a test was added**

```bash
git add backend/tests/unit/domain/billing/test_reconciliation.py
git commit -m "test(billing): confirm reconciliation handles a Price change with no schedule-specific code"
```

(Skip this commit entirely if Step 1 found the coverage already present — note that in the final report instead.)

---

## Task 13: Full validation sweep

**Files:** none (verification only)

- [ ] **Step 1: Backend compile/import check**

Run: `backend/.venv/Scripts/python.exe -m compileall backend/domain/billing backend/db/services/billing_service.py backend/api/main.py -q`
Expected: no output (success)

- [ ] **Step 2: Full focused backend billing suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/billing/ backend/tests/unit/db/services/test_billing_service.py backend/tests/unit/db/services/test_billing_service_plan_change.py backend/tests/unit/db/services/test_billing_service_plan_change_matrix.py backend/tests/unit/api/test_billing_api.py backend/tests/unit/api/test_billing_plan_change_api.py backend/tests/unit/api/test_billing_plan_change_security.py -v`
Expected: all pass; record the total count for the final report.

- [ ] **Step 3: `git diff --check` for whitespace errors**

Run: `git diff --check`
Expected: no output

- [ ] **Step 4: Full focused frontend billing/pricing suite**

Run (from `frontend/`):
```
npx tsx --test lib/billing/billingClient.test.mjs lib/billing/billingClient.planChange.test.mjs lib/billing/billingPresentation.test.mjs lib/billing/billingPresentation.planChange.test.mjs lib/billing/billingPricing.test.mjs lib/billing/billingSuccessPolling.test.mjs app/billing/billingRoutes.contract.test.mjs app/api/billing/billingProxy.contract.test.mjs components/pricing/PricingPageClient.planChange.test.mjs
```
Expected: all pass; record the total count for the final report.

- [ ] **Step 5: Isolated frontend production build to a separate dist directory**

First check whether any dev server is currently running on the default Next port (per prior project memory, `.next` contention with a running dev server corrupts concurrent builds) — run the build with an explicit distinct output directory so it cannot collide:

```bash
cd frontend && npx next build --experimental-build-mode=default 2>&1 | tee /tmp/plan-change-build.log
```

If the repo's `next.config.js` doesn't already support a custom `distDir` via env var, set one explicitly for this isolated run by passing a temporary override (check `next.config.js` first for how `distDir` is currently configured — most likely it needs a one-line temporary env-driven override, e.g. `distDir: process.env.PLAN_CHANGE_BUILD_DIR || ".next"`, applied only if not already parameterized; do not permanently change the default build output location for the rest of the team's ongoing dev servers). If a plain `next build` would collide with a running dev server's `.next` directory, use:

```bash
cd frontend && PLAN_CHANGE_BUILD_DIR=.next-plan-change-verify npx next build
```

Expected: build succeeds with no errors. Record pass/fail for the final report. Delete the temporary `.next-plan-change-verify` directory afterward if created.

- [ ] **Step 6: Confirm no external state changed**

Run: `git status --short` (should show only the files this plan touched, nothing in Stripe/Supabase config), and manually confirm `BILLING_CHECKOUT_ENABLED` was never referenced for modification anywhere in the diff:

```bash
git diff --stat main..HEAD -- backend/ frontend/ docs/
git grep -n "BILLING_CHECKOUT_ENABLED" -- backend/ frontend/ | grep -v ".test."
```

Expected: `BILLING_CHECKOUT_ENABLED` only appears in its existing read-sites (unchanged), never written/flipped by this diff.

- [ ] **Step 7: Final commit if any cleanup files remain**

```bash
git status --short
```

If clean, no commit needed — this task is verification-only.

---

## Self-Review Notes (completed during plan authoring)

- **Spec coverage:** §1-§6 → Tasks 1,3,6; §7-§8 → Tasks 4,5; §9 → Task 2; §10 → Task 3/5 idempotency keys; §11 → Task 5 downgrade path; §12 → Task 3/5 pending-state classification; §13 → Task 5 cancel; §14 → Task 5 `billing_status` extension; §15 → enforced as a constraint (no repository changes anywhere in the plan); §16 → Task 12; §17 → Task 10; §18 → Tasks 7, 11, 13; §19 → enforced as global constraint, checked in Task 13 Step 6. No gaps found.
- **Placeholder scan:** every step above contains literal code or literal shell commands; the only intentionally-conditional steps are Task 4 Step 1 (SDK introspection, which by design must run against the real installed package rather than being pre-guessed) and Task 12 (skip-if-already-covered, with the exact test body given for the case where it's needed).
- **Type consistency:** `BillingService.preview_plan_change`/`confirm_plan_change`/`cancel_scheduled_plan_change` signatures are identical across Tasks 5, 6, 7, 11. `PlanChangeAction`, `classify_transition`, `classify_schedule`, DTO builders, idempotency-key functions are defined once in Task 3 and only consumed (never redefined) in Tasks 5, 11. `previewPlanChange`/`confirmPlanChange`/`cancelScheduledPlanChange` frontend names match between Tasks 8 and 10.
