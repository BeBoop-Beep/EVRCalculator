from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[4]
CAPTURE = ROOT / ".github/workflows/treatment-set-relative-expansion-v2-capture.yml"
HIERARCHY = ROOT / ".github/workflows/treatment-set-relative-hierarchy-v2.yml"

FAILED_CAPTURE_RUN = "37061908972"
TARGET_FINGERPRINT = "28b344ca8ea95ba8fbc9fa947cdb28a1a3d83408482572084ee83e1cf992563d"


def _read(path: Path) -> str:
    assert path.exists(), f"missing workflow: {path}"
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> dict:
    payload = yaml.safe_load(_read(path))
    assert isinstance(payload, dict), f"invalid workflow mapping: {path}"
    assert isinstance(payload.get("jobs"), dict) and payload["jobs"], f"missing jobs: {path}"
    return payload


def test_workflow_yaml_and_bash_blocks_parse():
    for path in (CAPTURE, HIERARCHY):
        payload = _parse(path)
        for job_name, job in payload["jobs"].items():
            assert isinstance(job, dict), f"invalid job={job_name} path={path}"
            for step in job.get("steps") or []:
                script = step.get("run") if isinstance(step, dict) else None
                shell = str(step.get("shell") or "bash") if isinstance(step, dict) else "bash"
                if not script or not shell.startswith("bash"):
                    continue
                proc = subprocess.run(
                    ["bash", "-n"],
                    input=str(script),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                assert proc.returncode == 0, (
                    f"bash syntax failure path={path} job={job_name} "
                    f"step={step.get('name')} stderr={proc.stderr}"
                )


def test_capture_workflow_is_manual_vm_locked_and_reset_guarded():
    text = _read(CAPTURE)

    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text
    assert "runs-on: self-hosted" in text
    assert "/tmp/active-supply-panel.lock" in text
    assert "/tmp/pkmnprices-api.lock" in text
    assert "/tmp/pokemon-scrape-dispatcher.lock" in text
    assert "/tmp/pokemon-post-scrape-publication.lock" in text
    assert "2026-10-03" in text
    assert "TREATMENT_V2_REFUSING_BEFORE_CREDIT_RESET" in text
    assert "/home/ubuntu/state/db-safety/hold.json" in text
    assert "--credit-cap 22000" in text
    assert "--capture-authorization SET_RELATIVE_V2_FROZEN_CAPTURE_20261002" in text
    assert TARGET_FINGERPRINT in text
    assert FAILED_CAPTURE_RUN not in text


def test_capture_workflow_chains_same_run_artifact_into_estimator():
    text = _read(CAPTURE)

    assert "needs: capture" in text
    marker = "- name: Download this run's frozen fresh capture"
    assert marker in text
    section = text.split(marker, 1)[1].split(
        "- name: Download frozen prior independent replication panel", 1
    )[0]
    assert "treatment-set-relative-expansion-v2-capture" in section
    assert "run-id:" not in section

    assert "research_treatment_set_relative_hierarchy_v2.py" in text
    assert "run-id: 36971438903" in text


def test_fallback_estimator_requires_explicit_successful_capture_run():
    text = _read(HIERARCHY)

    assert "workflow_dispatch:" in text
    assert "capture_run_id:" in text
    assert "\n  push:" not in text
    assert FAILED_CAPTURE_RUN not in text
    assert 'CAPTURE_RUN_ID: ${{ inputs.capture_run_id }}' in text
    assert 'run-id: ${{ inputs.capture_run_id }}' in text
    assert 'p.get("conclusion") == "success"' in text
    assert (
        'expected_workflow = ".github/workflows/'
        'treatment-set-relative-expansion-v2-capture.yml"'
    ) in text
