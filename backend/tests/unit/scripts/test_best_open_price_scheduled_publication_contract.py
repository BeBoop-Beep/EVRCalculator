from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
TASK = REPO_ROOT / "infra" / "local" / "run_simulations_task.bat"
WRAPPER = REPO_ROOT / "infra" / "local" / "run_best_open_price.sh"


def test_best_open_is_part_of_existing_task_not_a_second_scheduler():
    task = TASK.read_text(encoding="utf-8")
    assert "run_simulations.sh" in task
    assert "run_best_open_price.sh" in task
    assert task.index("run_simulations.sh") < task.index("run_best_open_price.sh")
    # The expensive job only begins after the base simulation/publication task
    # captured a real zero exit code.
    assert 'if not "%RUN_EXIT%"=="0" goto finalize' in task


def test_best_open_failure_propagates_to_windows_task_exit_code():
    task = TASK.read_text(encoding="utf-8")
    best_open = task[task.index("run_best_open_price.sh") :]
    assert 'set "BEST_OPEN_EXIT=%ERRORLEVEL%"' in best_open
    assert 'if not "%BEST_OPEN_EXIT%"=="0" set "RUN_EXIT=%BEST_OPEN_EXIT%"' in best_open
    assert 'endlocal & exit /b %RUN_EXIT%' in task


def test_task_invokes_shell_through_bash_so_new_file_need_not_depend_on_exec_bit():
    task = TASK.read_text(encoding="utf-8")
    assert "bash ./infra/local/run_best_open_price.sh" in task


def test_recurring_wrapper_uses_validated_exact_batch_and_commit_mode():
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "python -m backend.scripts.publish_best_open_price_if_ready" in wrapper
    assert "--commit" in wrapper
    assert "--quantity-batch-size 24" in wrapper
    assert "logs/best_open_price_publication.json" in wrapper
    assert "logs/best_open_price_publication.log" in wrapper


def test_recurring_wrapper_refuses_missing_repo_or_venv_and_parses_dotenv_safely():
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert 'if [ ! -d "$REPO_DIR" ]; then' in wrapper
    assert "if [ ! -f backend/.venv/Scripts/activate ]; then" in wrapper
    assert 'dotenv_values("backend/.env")' in wrapper
    assert "source backend/.env" not in wrapper


def test_recurring_wrapper_has_distinct_success_failure_and_noop_notifications():
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "PUBLISHED)" in wrapper
    assert "ALREADY_CURRENT)" in wrapper
    assert "Best-Open Price publication completed" in wrapper
    assert "Best-Open Price publication failed or was blocked" in wrapper
    noop = wrapper[wrapper.index("ALREADY_CURRENT)") : wrapper.index(";;", wrapper.index("ALREADY_CURRENT)"))]
    assert "notify_slack" not in noop
