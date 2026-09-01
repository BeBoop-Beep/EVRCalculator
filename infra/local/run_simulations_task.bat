@echo off
REM ============================================================================
REM Windows Task Scheduler entry point for the daily simulation + publication.
REM
REM THIS SCRIPT MAY NEVER RUN IN LOCAL MODE.
REM
REM It used to `cd /d D:\EVRCalculator` and invoke run_simulations.sh with no
REM environment at all. run_simulations.sh defaults to LOCAL checkout mode, which
REM deliberately permits a feature branch, tracked uncommitted changes, and a
REM HEAD that differs from origin/main - because local mode exists to exercise
REM whatever the developer currently has in the tree. That is correct for a
REM developer at a keyboard and unacceptable for an unattended job that publishes
REM public snapshots: the nightly publication would ship whatever happened to be
REM checked out in the development tree at 3am.
REM
REM The four variables below opt into the fail-closed production path. With them
REM set, run_simulations.sh REFUSES (exit 2, with a Slack notification) when:
REM   - the production worktree does not exist;
REM   - the branch is not main;
REM   - HEAD differs from origin/main;
REM   - tracked working-tree changes exist;
REM   - HEAD cannot be resolved;
REM   - the virtual environment is unavailable.
REM It never checks out another branch, never stashes, and never resets anything.
REM
REM ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT is deliberately NOT set here. It is the
REM manual emergency override and setting it from a scheduled task would restore
REM exactly the behaviour this file exists to remove.
REM
REM One-time setup of the production worktree is in the repository README for
REM this directory; this script creates nothing and modifies no checkout.
REM ============================================================================

setlocal

set "EVR_PRODUCTION_WINDOWS_DIR=D:\EVRCalculator-production"
set "EVR_PRODUCTION_REPO_DIR=/d/EVRCalculator-production"
set "EVR_PUBLICATION_CHECKOUT_MODE=production"
set "EXPECTED_PUBLICATION_BRANCH=main"
set "PUBLICATION_FETCH_ORIGIN=0"

REM Logs live with the production checkout, not with the development tree, so a
REM scheduled failure is never diagnosed against the wrong repository.
if not exist "%EVR_PRODUCTION_WINDOWS_DIR%" (
    echo Production worktree missing: %EVR_PRODUCTION_WINDOWS_DIR%
    echo Refusing to fall back to the development checkout.
    exit /b 2
)

cd /d "%EVR_PRODUCTION_WINDOWS_DIR%"

if not exist logs mkdir logs

echo ================================ >> logs\task_scheduler_debug.log
echo Task started at %date% %time% >> logs\task_scheduler_debug.log
echo Current dir: %CD% >> logs\task_scheduler_debug.log
echo Checkout mode: %EVR_PUBLICATION_CHECKOUT_MODE% >> logs\task_scheduler_debug.log
echo Expected branch: %EXPECTED_PUBLICATION_BRANCH% >> logs\task_scheduler_debug.log

"C:\Program Files\Git\usr\bin\bash.exe" -lc "cd %EVR_PRODUCTION_REPO_DIR% && ./infra/local/run_simulations.sh" >> logs\task_scheduler_debug.log 2>&1

REM Captured IMMEDIATELY. Every command in between - including `echo` - resets
REM ERRORLEVEL to 0, so reading it after the log lines below would report a
REM successful task for every possible failure of the job it just ran.
set "RUN_EXIT=%ERRORLEVEL%"

echo Task finished at %date% %time% with exit code %RUN_EXIT% >> logs\task_scheduler_debug.log
echo ================================ >> logs\task_scheduler_debug.log

endlocal & exit /b %RUN_EXIT%
