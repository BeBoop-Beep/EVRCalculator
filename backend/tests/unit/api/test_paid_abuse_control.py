import json
import logging

from backend.api.paid_abuse_control import (
    POLICY_CUSTOM_QUERY, POLICY_INTERACTIVE_DETAIL, POLICY_RANKED_INTELLIGENCE,
    PaidAnalyticsLimiter,
)


def test_query_variations_share_user_policy_bucket_and_return_retry_after():
    now = [100.0]
    limiter = PaidAnalyticsLimiter(clock=lambda: now[0])
    decisions = [limiter.check(
        policy_name=POLICY_CUSTOM_QUERY, user_id="user-a", route="/market/explorer/query",
        headers={"x-forwarded-for": "203.0.113.1"}, client_host=None, request_id=str(i),
    ) for i in range(6)]
    assert all(item.allowed for item in decisions[:5])
    assert not decisions[5].allowed
    assert decisions[5].retry_after_seconds == 10


def test_different_users_are_isolated():
    limiter = PaidAnalyticsLimiter(clock=lambda: 100.0)
    for i in range(12):
        assert limiter.check(policy_name=POLICY_RANKED_INTELLIGENCE, user_id="abusive",
                             route="rankings", headers={}, client_host="one", request_id=str(i)).allowed
    assert not limiter.check(policy_name=POLICY_RANKED_INTELLIGENCE, user_id="abusive",
                             route="rankings", headers={}, client_host="one", request_id="limited").allowed
    assert limiter.check(policy_name=POLICY_RANKED_INTELLIGENCE, user_id="legitimate",
                         route="rankings", headers={}, client_host="two", request_id="ok").allowed


def test_sustained_window_limits_requests_that_stay_below_burst_rate():
    now = [0.0]
    limiter = PaidAnalyticsLimiter(clock=lambda: now[0])
    for i in range(30):
        for _ in range(10):
            assert limiter.check(
                policy_name=POLICY_INTERACTIVE_DETAIL, user_id="steady-harvester",
                route="detail", headers={}, client_host="one", request_id=str(i),
            ).allowed
        now[0] += 11
    decision = limiter.check(
        policy_name=POLICY_INTERACTIVE_DETAIL, user_id="steady-harvester",
        route="another-alias", headers={}, client_host="one", request_id="limited",
    )
    assert not decision.allowed
    assert decision.reason == "user_sustained"
    assert decision.retry_after_seconds > 0


def test_representative_human_flow_stays_below_shared_policy_budgets():
    limiter = PaidAnalyticsLimiter(clock=lambda: 100.0)
    flow = ["rankings", "rankings-sort", "set", "product", "filters", "card-1", "card-2"]
    for index, route in enumerate(flow):
        policy = POLICY_RANKED_INTELLIGENCE if route.startswith("rankings") else POLICY_INTERACTIVE_DETAIL
        assert limiter.check(policy_name=policy, user_id="human", route=route,
                             headers={}, client_host="human-network", request_id=str(index)).allowed


def test_telemetry_contains_no_request_secrets(caplog):
    limiter = PaidAnalyticsLimiter(clock=lambda: 100.0)
    with caplog.at_level(logging.INFO, logger="security.paid_analytics"):
        limiter.check(policy_name=POLICY_CUSTOM_QUERY, user_id="private-user-id",
                      route="custom", headers={"authorization": "Bearer secret", "cookie": "token=secret"},
                      client_host="198.51.100.2", request_id="request-1")
    record = json.loads(caplog.records[-1].message)
    assert "accountPseudonym" in record
    assert "private-user-id" not in caplog.text
    assert "Bearer secret" not in caplog.text
    assert "token=secret" not in caplog.text
