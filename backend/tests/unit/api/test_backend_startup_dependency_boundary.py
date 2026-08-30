import ast
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICE_PATH = REPO_ROOT / "backend/db/services/treatment_market_prestige_v3_service.py"
RESEARCH_PREFIX = "backend.scripts.build_treatment_market_prestige_v3_round"


def test_production_service_has_no_module_level_research_builder_imports():
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    imports = []

    def collect_module_scope(nodes):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            else:
                for child in ast.iter_child_nodes(node):
                    collect_module_scope([child])

    collect_module_scope(tree.body)

    assert not [name for name in imports if name.startswith(RESEARCH_PREFIX)]


def test_fastapi_startup_does_not_import_research_stack_or_scipy():
    script = f"""
import builtins
import sys

blocked = ({RESEARCH_PREFIX!r}, "scipy")
original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == blocked[1] or name.startswith(blocked[0]):
        raise ModuleNotFoundError(f"startup imported research-only dependency: {{name}}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import backend.api.main

loaded = [name for name in sys.modules if name == "scipy" or name.startswith(blocked[0])]
if loaded:
    raise AssertionError(f"research-only modules loaded during startup: {{loaded}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
