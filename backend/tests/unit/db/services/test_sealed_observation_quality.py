from backend.db.services.sealed_observation_quality import (
    CURRENT,
    ONE_DAY_CARRY,
    UNAVAILABLE,
    assess_sealed_observation_quality,
)
from backend.db.services import sealed_observation_quality as service


def quality(**overrides):
    values = dict(
        market_date="2026-08-24", expected_count=100, observed_count=100,
        previous_observed_count=100, two_days_prior_observed_count=100,
        last_observed_date="2026-08-23",
    )
    values.update(overrides)
    return assess_sealed_observation_quality(**values)


def test_quality_is_current_with_real_consecutive_daily_observations():
    assert quality()["state"] == CURRENT


def test_quality_identifies_the_single_previous_close_gap():
    result = quality(previous_observed_count=0, last_observed_date="2026-08-22")
    assert result["state"] == ONE_DAY_CARRY
    assert result["comparisonCarrySourceDate"] == "2026-08-22"


def test_zero_current_day_is_unavailable_and_alert_eligible():
    result = quality(
        market_date="2026-08-23", observed_count=0,
        previous_observed_count=100, two_days_prior_observed_count=100,
        last_observed_date="2026-08-22",
    )
    assert result["state"] == UNAVAILABLE
    assert result["carryForwardEligible"] is True


def test_multi_day_gap_is_never_carry_eligible():
    result = quality(observed_count=0, previous_observed_count=0,
                     two_days_prior_observed_count=0, last_observed_date="2026-08-20")
    assert result["state"] == UNAVAILABLE
    assert result["carryForwardEligible"] is False


def test_zero_observation_day_queues_existing_operations_alert(monkeypatch):
    diagnosed = quality(
        market_date="2026-08-23", observed_count=0,
        last_observed_date="2026-08-22",
    )
    queued = []
    monkeypatch.setattr(service, "read_sealed_observation_quality", lambda *_a: diagnosed)
    from backend.alerts import scrape_alerts
    monkeypatch.setattr(scrape_alerts, "alert_sealed_market_observation_gap", queued.append)
    assert service.evaluate_and_alert_sealed_observation_quality(object(), "2026-08-23") == diagnosed
    assert queued == [diagnosed]
