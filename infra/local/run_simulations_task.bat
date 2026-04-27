@echo off
cd /d D:\EVRCalculator

if not exist logs mkdir logs

echo ================================ >> logs\task_scheduler_debug.log
echo Task started at %date% %time% >> logs\task_scheduler_debug.log
echo Current dir: %CD% >> logs\task_scheduler_debug.log

"C:\Program Files\Git\usr\bin\bash.exe" -lc "cd /d/EVRCalculator && ./infra/local/run_simulations.sh" >> logs\task_scheduler_debug.log 2>&1

echo Task finished at %date% %time% with exit code %ERRORLEVEL% >> logs\task_scheduler_debug.log
echo ================================ >> logs\task_scheduler_debug.log

exit /b %ERRORLEVEL%