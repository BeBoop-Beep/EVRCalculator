from backend.scripts.validate_alerting_deployment import validate_schedule_text


def test_deploy_validation_requires_both_independent_schedules():
    only_dispatcher = "* * * * * python -m backend.alerts.dispatcher"
    result = validate_schedule_text(only_dispatcher)
    assert result["healthy"] is False
    assert result["missing_commands"] == ["backend.alerts.market_freshness_watchdog"]


def test_deploy_validation_accepts_dispatcher_and_watchdog():
    crontab = "\n".join([
        "* * * * * python -m backend.alerts.dispatcher",
        "*/5 * * * * python -m backend.alerts.market_freshness_watchdog",
    ])
    assert validate_schedule_text(crontab) == {"healthy": True, "missing_commands": []}
