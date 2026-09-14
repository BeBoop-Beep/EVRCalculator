from backend.scripts.validate_alerting_deployment import validate_schedule_text


DISPATCHER = "backend.alerts.dispatcher"
WATCHDOG = "backend.alerts.market_freshness_watchdog"


def _dispatcher(command="python -m backend.alerts.dispatcher"):
    return f"* * * * * /usr/bin/flock -n /tmp/evr-alert-dispatcher.lock -c '{command}'"


def _watchdog(command="python -m backend.alerts.market_freshness_watchdog"):
    return f"*/5 * * * * flock -n /tmp/evr-market-watchdog.lock sh -c '{command}'"


def test_deploy_validation_requires_both_independent_schedules():
    result = validate_schedule_text(_dispatcher())
    assert result["healthy"] is False
    assert result["missing_commands"] == [WATCHDOG]
    assert f"{WATCHDOG}:missing_active_schedule" in result["issues"]


def test_commented_out_commands_do_not_satisfy_contract():
    crontab = "\n".join([
        "# * * * * * flock -n /tmp/a python -m backend.alerts.dispatcher",
        "   # */5 * * * * flock -n /tmp/b python -m backend.alerts.market_freshness_watchdog",
    ])
    result = validate_schedule_text(crontab)
    assert result["healthy"] is False
    assert result["missing_commands"] == [DISPATCHER, WATCHDOG]


def test_dispatcher_without_nonblocking_flock_is_rejected():
    crontab = "\n".join([
        "* * * * * python -m backend.alerts.dispatcher",
        _watchdog(),
    ])
    result = validate_schedule_text(crontab)
    assert result["healthy"] is False
    assert f"{DISPATCHER}:missing_nonblocking_flock" in result["issues"]
    assert result["schedules"][DISPATCHER]["cadence_ok"] is True
    assert result["schedules"][DISPATCHER]["nonblocking_flock"] is False


def test_watchdog_without_nonblocking_flock_is_rejected():
    crontab = "\n".join([
        _dispatcher(),
        "*/5 * * * * python -m backend.alerts.market_freshness_watchdog",
    ])
    result = validate_schedule_text(crontab)
    assert result["healthy"] is False
    assert f"{WATCHDOG}:missing_nonblocking_flock" in result["issues"]


def test_wrong_cadence_is_rejected_even_when_command_and_flock_exist():
    crontab = "\n".join([
        "*/2 * * * * flock -n /tmp/a python -m backend.alerts.dispatcher",
        _watchdog(),
    ])
    result = validate_schedule_text(crontab)
    assert result["healthy"] is False
    assert f"{DISPATCHER}:wrong_cadence" in result["issues"]


def test_deploy_validation_accepts_canonical_locked_pair():
    crontab = "\n".join([
        "CRON_TZ=America/Phoenix",
        "17 4 * * * echo unrelated",
        _dispatcher("cd /srv/app && .venv/bin/python -m backend.alerts.dispatcher"),
        _watchdog("cd /srv/app && .venv/bin/python -m backend.alerts.market_freshness_watchdog"),
    ])
    result = validate_schedule_text(crontab)
    assert result["healthy"] is True
    assert result["missing_commands"] == []
    assert result["issues"] == []
    assert all(values["present"] for values in result["schedules"].values())
    assert all(values["cadence_ok"] for values in result["schedules"].values())
    assert all(values["nonblocking_flock"] for values in result["schedules"].values())


def test_whitespace_and_absolute_flock_path_are_accepted():
    crontab = "\n".join([
        "  *   *  * * *   /usr/bin/flock   -n /tmp/a sh -c 'python -m backend.alerts.dispatcher'  ",
        " */5  * * * * /bin/flock -n /tmp/b sh -c 'python -m backend.alerts.market_freshness_watchdog' ",
    ])
    assert validate_schedule_text(crontab)["healthy"] is True
