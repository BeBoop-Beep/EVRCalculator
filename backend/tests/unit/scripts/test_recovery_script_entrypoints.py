import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = (
    "repair_pokemon_set_value_history",
    "recover_pokemon_market_date",
)


@pytest.mark.parametrize("script_name", SCRIPTS)
@pytest.mark.parametrize("invocation", ("direct", "module"))
def test_recovery_entrypoint_starts_from_repository_root_without_pythonpath(script_name, invocation):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    command = (
        [sys.executable, f"backend/scripts/{script_name}.py", "--help"]
        if invocation == "direct"
        else [sys.executable, "-m", f"backend.scripts.{script_name}", "--help"]
    )
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
