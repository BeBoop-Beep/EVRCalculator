import json
import math
from pathlib import Path

from backend.scripts.run_index_fair_value_f2_study import (
    EXPECTED_FINGERPRINT,
    SEED,
    band,
    canonical_hash,
    metrics,
)

ROOT = Path("backend/artifacts/index_fair_value")


def test_exact_dataset_and_authority_bindings() -> None:
    payload = json.loads((ROOT / "index_fair_value_f1_dataset.json").read_text(encoding="utf-8"))
    assert payload["manifest"]["datasetFingerprint"] == EXPECTED_FINGERPRINT
    assert payload["manifest"]["authorityBindings"]["collectorModelRunId"] == "e282f26e-2136-4105-b0a3-f0974c4d9d70"
    assert payload["manifest"]["authorityBindings"]["treatmentTaxonomyVersion"] == "pokemon_card_treatment_taxonomy_v3"


def test_outer_folds_are_complete_and_disjoint() -> None:
    manifest = json.loads((ROOT / "index_fair_value_f2_fold_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["folds"]) == 22
    seen = set()
    for fold in manifest["folds"]:
        ids = set(fold["cardIds"])
        assert not seen.intersection(ids)
        seen.update(ids)
    assert len(seen) == 4349
    assert manifest["foldFingerprint"] == canonical_hash(manifest["folds"])


def test_target_is_not_a_registered_feature() -> None:
    source = Path("backend/scripts/run_index_fair_value_f2_study.py").read_text(encoding="utf-8")
    feature_lines = [line for line in source.splitlines() if line.startswith("NUM =") or line.startswith("CAT =")]
    assert all("price" not in line for line in feature_lines)
    assert "random_state=SEED" in source and SEED == 20260911


def test_price_bands_and_back_transform_metrics() -> None:
    assert [band(x) for x in (4.99, 5, 9.99, 10, 24.99, 25, 49.99, 50, 99.99, 100, 249.99, 250)] == [
        "under_5", "5_to_under_10", "5_to_under_10", "10_to_under_25", "10_to_under_25",
        "25_to_under_50", "25_to_under_50", "50_to_under_100", "50_to_under_100",
        "100_to_under_250", "100_to_under_250", "250_plus"]
    result = metrics([math.exp(1), math.exp(2)], [math.exp(1), math.exp(2)])
    assert result["MdAPE"] == 0 and result["within10Pct"] == 100


def test_oof_predictions_are_complete_and_unique_per_model() -> None:
    import pandas as pd
    rows = pd.read_csv(ROOT / "index_fair_value_f2_oof_predictions.csv")
    assert set(rows.model) >= {"B0","B1","B2","B3","B4","B5","B6","B7","ModelA","ModelB","ModelC","ModelD"}
    for _, group in rows.groupby("model"):
        assert len(group) == 4349
        assert group.canonical_card_id.nunique() == 4349


def test_no_database_or_production_mutations() -> None:
    source = Path("backend/scripts/run_index_fair_value_f2_study.py").read_text(encoding="utf-8")
    for forbidden in (".insert({", ".upsert(", ").update(", ").delete(", ".rpc("):
        assert forbidden not in source
