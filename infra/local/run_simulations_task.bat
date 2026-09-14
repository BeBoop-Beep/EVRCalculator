@echo off
REM ============================================================================
REM Windows Task Scheduler entry point for the daily simulation + publication.
REM
REM The scheduled job intentionally runs from the active local checkout at
REM D:\EVRCalculator. This repository uses one active development branch at
REM a time and that branch changes as work advances, so the scheduler must never
REM pin a branch name, switch branches, stash, reset, or require a second
REM hard-coded worktree.
REM
REM run_simulations.sh LOCAL mode records the actual branch, HEAD, working-tree
REM state, Python environment, and publication result on every invocation. Those
REM Git values are diagnostics only; they are not reasons to refuse a scheduled
REM run. Real startup failures (missing repo/venv) and simulation/publication
REM failures still propagate a non-zero exit code.
REM
REM Best-Open Price is NOT a second scheduled task. Once the normal daily
REM publication (including Budget Ranking) exits successfully, this same Task
REM Scheduler invocation runs the bounded Best-Open prepared-data wrapper. A
REM failure there keeps the task non-successful instead of silently serving a
REM stale Full Market threshold indefinitely.
REM ============================================================================

setlocal

set "EVR_PRODUCTION_WINDOWS_DIR=D:\EVRCalculator"
set "EVR_PRODUCTION_REPO_DIR=/d/EVRCalculator"
set "EVR_PUBLICATION_CHECKOUT_MODE=local"
set "PUBLICATION_FETCH_ORIGIN=0"

REM Fail loudly if the configured local repository itself is unavailable. There
REM is deliberately no fallback path and no branch mutation here.
if not exist "%EVR_PRODUCTION_WINDOWS_DIR%" (
    echo Repository missing: %EVR_PRODUCTION_WINDOWS_DIR%
    exit /b 2
)

cd /d "%EVR_PRODUCTION_WINDOWS_DIR%"

if not exist logs mkdir logs

echo ================================ >> logs\task_scheduler_debug.log
echo Task started at %date% %time% >> logs\task_scheduler_debug.log
echo Current dir: %CD% >> logs\task_scheduler_debug.log
echo Checkout mode: %EVR_PUBLICATION_CHECKOUT_MODE% >> logs\task_scheduler_debug.log

"C:\Program Files\Git\usr\bin\bash.exe" -lc "cd %EVR_PRODUCTION_REPO_DIR% && ./infra/local/run_simulations.sh" >> logs\task_scheduler_debug.log 2>&1

REM Captured IMMEDIATELY. Every command in between - including `echo` - resets
REM ERRORLEVEL to 0, so reading it after the log lines below would report a
REM successful task for every possible failure of the job it just ran.
set "RUN_EXIT=%ERRORLEVEL%"

REM Only a fully successful base publication is allowed to launch the expensive
REM (~hour at the validated 138-SKU scale) Best-Open preparation. The Budget
REM Ranking publisher is already inside run_simulations.sh, so this guarantees
REM the threshold engine sees the day's final published Full Market authority.
if not "%RUN_EXIT%"=="0" goto finalize

echo Best-Open publication started at %date% %time% >> logs\task_scheduler_debug.log
"C:\Program Files\Git\usr\bin\bash.exe" -lc "cd %EVR_PRODUCTION_REPO_DIR% && bash ./infra/local/run_best_open_price.sh" >> logs\task_scheduler_debug.log 2>&1
set "BEST_OPEN_EXIT=%ERRORLEVEL%"
if not "%BEST_OPEN_EXIT%"=="0" set "RUN_EXIT=%BEST_OPEN_EXIT%"

:finalize
echo Task finished at %date% %time% with exit code %RUN_EXIT% >> logs\task_scheduler_debug.log
echo ================================ >> logs\task_scheduler_debug.log

endlocal & exit /b %RUN_EXIT%