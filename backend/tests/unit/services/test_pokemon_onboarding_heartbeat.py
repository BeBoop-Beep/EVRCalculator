import time

from backend.services.pokemon_onboarding_heartbeat import LeaseHeartbeat


def test_long_step_heartbeats_multiple_times_and_stops():
    calls = []
    with LeaseHeartbeat(lambda: calls.append(time.time()) or {"id": "job"}, lease_seconds=1, interval_seconds=0.01) as hb:
        time.sleep(0.04)
    count = len(calls)
    assert count >= 2
    time.sleep(0.03)
    assert len(calls) == count
    assert hb.failure is None


def test_lost_ownership_and_failure_are_visible():
    with LeaseHeartbeat(lambda: None, lease_seconds=1, interval_seconds=0.01) as lost:
        time.sleep(0.02)
    assert lost.lost_ownership is True

    def fail():
        raise RuntimeError("db down")
    with LeaseHeartbeat(fail, lease_seconds=1, interval_seconds=0.01) as failed:
        time.sleep(0.02)
    assert isinstance(failed.failure, RuntimeError)
