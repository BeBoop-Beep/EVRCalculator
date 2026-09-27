import json

import pytest

from backend.scripts import research_financial_rip_v5_control_checkpoint as checkpoint_runner


def test_resume_skips_completed_product_and_preserves_interrupted_evidence(tmp_path, monkeypatch):
    checkpoint = tmp_path / "control.json"
    calls = []

    def fake_run(_client, **kwargs):
        calls.append(set(kwargs["skip_product_ids"]))
        if not calls[-1]:
            kwargs["checkpoint_callback"]({"sealedProductId": "first", "resolved": True})
            raise RuntimeError("simulated interruption")
        return {"status": "complete"}

    monkeypatch.setattr(checkpoint_runner, "get_client", lambda: object())
    monkeypatch.setattr(checkpoint_runner.research_v2, "run", fake_run)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        checkpoint_runner.run(restart=True, checkpoint=checkpoint)
    assert json.loads(checkpoint.read_text())["products"][0]["sealedProductId"] == "first"
    checkpoint_runner.run(resume=True, checkpoint=checkpoint)
    assert calls == [set(), {"first"}]
    assert len(json.loads(checkpoint.read_text())["products"]) == 1


def test_control_resume_refuses_authority_mismatch(tmp_path, monkeypatch):
    checkpoint = tmp_path / "control.json"
    checkpoint.write_text(json.dumps({"sourceSnapshotId": "wrong"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="sourceSnapshotId"):
        checkpoint_runner.run(resume=True, checkpoint=checkpoint)
