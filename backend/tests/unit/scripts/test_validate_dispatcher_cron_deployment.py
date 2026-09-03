from backend.scripts.validate_dispatcher_cron_deployment import (
    validate_dispatcher_schedule_text,
)

CANONICAL_LOCKED_LINE = (
    "* * * * * /usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c "
    "'cd /home/ubuntu/repos/EVRCalculator && "
    "/home/ubuntu/repos/EVRCalculator/.venv/bin/python backend/scripts/run_next_scrape_job.py' "
    ">> backend/logs/cron_dispatcher.log 2>&1"
)

UNLOCKED_LINE = (
    "* * * * * cd /home/ubuntu/repos/EVRCalculator && "
    ".venv/bin/python backend/scripts/run_next_scrape_job.py "
    ">> backend/logs/cron_dispatcher.log 2>&1"
)

LEGACY_1PM_LINE = (
    "0 13 * * * cd /home/ubuntu/repos/EVRCalculator && .venv/bin/python "
    "backend/scripts/build_pokemon_market_dashboard_snapshots.py --all --commit "
    "--days 365 --window 365d"
)


def test_canonical_locked_dispatcher_is_healthy():
    report = validate_dispatcher_schedule_text(CANONICAL_LOCKED_LINE)
    assert report.healthy is True
    assert report.dispatcher_lines_found == 1
    assert report.unlocked_dispatcher_lines == []
    assert report.reasons == []


def test_every_minute_dispatcher_without_flock_fails():
    """This is the exact Sep 2-3, 2026 incident shape and MUST fail deploy."""
    report = validate_dispatcher_schedule_text(UNLOCKED_LINE)
    assert report.healthy is False
    assert report.unlocked_dispatcher_lines == [UNLOCKED_LINE]
    assert any("flock" in reason for reason in report.reasons)


def test_missing_dispatcher_entirely_fails():
    report = validate_dispatcher_schedule_text("# nothing scheduled\n")
    assert report.healthy is False
    assert report.dispatcher_lines_found == 0
    assert any("no crontab entry" in reason for reason in report.reasons)


def test_legacy_1pm_dashboard_rebuild_fails_even_when_dispatcher_is_locked():
    text = "\n".join([CANONICAL_LOCKED_LINE, LEGACY_1PM_LINE])
    report = validate_dispatcher_schedule_text(text)
    assert report.healthy is False
    assert report.legacy_dashboard_rebuild_lines == [LEGACY_1PM_LINE]
    assert any("legacy 1PM" in reason for reason in report.reasons)


def test_flock_dash_dash_nonblock_long_form_is_also_accepted():
    line = UNLOCKED_LINE.replace(
        "python backend/scripts/run_next_scrape_job.py",
        "flock --nonblock /tmp/pokemon-scrape-dispatcher.lock -c 'python backend/scripts/run_next_scrape_job.py'",
    )
    report = validate_dispatcher_schedule_text(line)
    assert report.healthy is True


def test_commented_out_unlocked_line_is_ignored():
    report = validate_dispatcher_schedule_text(f"# {UNLOCKED_LINE}")
    assert report.dispatcher_lines_found == 0
    assert report.healthy is False  # still fails: no active dispatcher scheduled
    assert report.unlocked_dispatcher_lines == []


def test_non_every_minute_locked_dispatcher_is_not_flagged_as_unlocked():
    """A non-every-minute schedule (e.g. a manual recovery entry) doesn't hit
    the every-minute overlap-accumulation failure mode this check targets."""
    line = UNLOCKED_LINE.replace("* * * * *", "*/5 * * * *")
    report = validate_dispatcher_schedule_text(line)
    assert report.unlocked_dispatcher_lines == []
