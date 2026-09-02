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
