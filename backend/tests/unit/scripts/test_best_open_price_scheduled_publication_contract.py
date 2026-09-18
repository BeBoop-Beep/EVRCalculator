"""Execute the actual downstream shell block against isolated stub commands."""
from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[4]
TASK = ROOT / 'infra/local/run_simulations_task.bat'
SCRIPT = ROOT / 'infra/local/run_simulations.sh'
WRAPPER = ROOT / 'infra/local/run_best_open_price.sh'


def test_both_manual_and_windows_paths_use_one_post_budget_hook():
    task, script = TASK.read_text(), SCRIPT.read_text()
    assert 'run_simulations.sh' in task
    assert 'run_best_open_price.sh' not in task
    assert script.count('bash ./infra/local/run_best_open_price.sh') == 1
    assert script.index('publish_budget_product_rankings_if_ready') < script.index('bash ./infra/local/run_best_open_price.sh')


@pytest.mark.parametrize('status,budget_exit,unrelated_exit,expected',[
    ('PUBLISHED',0,0,True),('PUBLISHED',0,1,True),
    ('NO_NEW_AUTHORITY',0,1,True),('UPSTREAM_NOT_READY',0,0,False),
    ('POST_PUBLISH_VERIFICATION_FAILED',1,0,False),('NOT_RUN',0,0,False),
])
def test_actual_hook_gates_on_budget_not_unrelated_audits(tmp_path,status,budget_exit,unrelated_exit,expected):
    (tmp_path/'infra/local').mkdir(parents=True); (tmp_path/'logs').mkdir()
    (tmp_path/'infra/local/run_best_open_price.sh').write_text('echo yes > invoked\nexit 7\n')
    script=SCRIPT.read_text(); start=script.index('BEST_OPEN_EXIT=0'); end=script.index('# The ONLY success notification.',start)
    block=script[start:end]
    env={**os.environ,'BUDGET_RANKING_EXIT':str(budget_exit),'BUDGET_RANKING_STATUS':status,
         'BUDGET_RANKING_REPORT':str(tmp_path/'absent.json'),'PUBLICATION_EXIT':str(unrelated_exit)}
    result=subprocess.run(['bash','-c',block+'\nexit "$BEST_OPEN_EXIT"'],cwd=tmp_path,env=env,check=False,capture_output=True,text=True)
    assert (tmp_path/'invoked').exists() is expected
    assert result.returncode == (7 if expected else 0), result.stderr


def test_failure_preserves_base_exit_and_task_stays_non_successful():
    task, script = TASK.read_text(), SCRIPT.read_text()
    assert 'endlocal & exit /b %RUN_EXIT%' in task
    assert '[ "$BEST_OPEN_EXIT" -ne 0 ]' in script
    assert '[ "$BUDGET_RANKING_EXIT" -eq 0 ] && [ "$BEST_OPEN_EXIT" -eq 0 ]' in script


def test_wrapper_reads_only_invocation_local_report_and_checks_exit():
    wrapper=WRAPPER.read_text()
    assert 'REPORT=$(mktemp ' in wrapper
    assert 'if [ "$RUN_EXIT" -ne 0 ]' in wrapper
    assert 'PROCESS_FAILED_AFTER_REPORT' in wrapper
    assert '--quantity-batch-size 24' in wrapper
    assert 'source backend/.env' not in wrapper
    assert 'dotenv_values("backend/.env")' in wrapper
