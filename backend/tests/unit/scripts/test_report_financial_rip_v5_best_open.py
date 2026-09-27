import json

import numpy as np

from backend.scripts import report_financial_rip_v5_best_open as report


def test_trajectory_audit_checks_adjacent_cents_and_source_authority(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    authority = {key: "same" for key in (
        "sourceSnapshotId", "sourceFingerprint", "sourceAuthorityFingerprint",
        "candidateVersion", "overallShadowVersion", "searchMethodIdentity")}
    np.savez(tmp_path / "p.npz", priceCents=[100, 99, 98], quantity=[1, 1, 2],
             pWin=[.1, .2, .5], typical=[10, 11, 20], loss=[5, 6, 8],
             shortfall=[12, 13, 22], trueWin=[5, 10, 100],
             v4=[30, 31, 34], v5=[32, 33, 35], overallV12=[40, 41, 43],
             overallV5=[42, 43, 45], p50Value=[1, 1, 2],
             committedCapital=[1, .99, 1.96])
    path.write_text(json.dumps({**authority,
        "collectorCheckpoint": {"trajectoryFiles": ["p.npz"]}}), encoding="utf-8")
    monkeypatch.setattr(report, "CHECKPOINT", path)
    result = report.trajectory_audit({**authority,
        "products": [{"sealedProductId": "p"}]})
    assert result["sameQuantityAdjacentCents"] == 1
    assert result["quantityBoundaryAdjacentCents"] == 1
    assert result["highWinStates"] == 1
    assert result["sameQuantityV5ScoreInversions"] == 0


def test_high_win_anchor_pair_keeps_price_to_component_delta_chain():
    def state(price, pwin, score):
        return {"priceCents": price, "quantity": 2,
                "chanceToRecoverCapital": pwin, "typicalRetentionScore": score,
                "trueWinFrequencyScore": 100, "lossResilienceScore": 80,
                "shortfallResilienceScore": score + 5,
                "financialRipV4Score": score + 10,
                "financialRipV5CandidateScore": score + 12}
    domain = {"trajectoryAnchors": {"p": [state(100, .5, 50), state(90, .7, 55)]}}
    pair = report.high_win_anchor_pairs(domain)[0]
    assert pair["deltaPriceCents"] == -10
    assert pair["deltaPWin"] == .7 - .5
    assert pair["deltaLoss"] == 0
    assert pair["deltaShortfall"] == 5
