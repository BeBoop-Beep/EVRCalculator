import pandas as pd
import pytest

from backend.scripts import run_index_fair_value_f2r_study as study


def row(card_id="target", root="set-a", name="Pikachu"):
    return pd.Series({
        "canonical_card_id": card_id, "root_set_id": root, "card_name": name,
        "negative_log10_pull_probability": 2.0, "collector_appeal": 80.0,
        "treatment_key": "SIR", "rarity_label": "rare", "structural_log": 1.0,
    })


def frame():
    return pd.DataFrame([
        {**row("target").to_dict(), "log_price": 9.0, "structural_residual": 8.0},
        {**row("p1").to_dict(), "log_price": 1.0, "structural_residual": 0.0},
        {**row("p2", name="Pikachu").to_dict(), "log_price": 2.0, "structural_residual": 1.0},
        {**row("p3", root="set-b").to_dict(), "log_price": 7.0, "structural_residual": 6.0},
        {**row("p4", name="Raichu").to_dict(), "log_price": 3.0, "structural_residual": 2.0},
    ])


def test_target_and_other_root_are_excluded_from_peer_aggregation():
    peers = study.peer_pool(frame(), row(), "target_only")
    assert set(peers.canonical_card_id) == {"p1", "p2", "p4"}
    predicted, count, _ = study.predict(row(), peers, "C0_set_median")
    assert count == 3
    assert predicted == pytest.approx(2.718281828 ** 2, rel=1e-6)


def test_related_family_excludes_same_card_name():
    peers = study.peer_pool(frame(), row(), "related_family")
    assert set(peers.canonical_card_id) == {"p4"}


def test_peer_selection_is_deterministic_and_leave_many_out_removes_nearest():
    first = study.peer_pool(frame(), row(), "random_20").canonical_card_id.tolist()
    second = study.peer_pool(frame(), row(), "random_20").canonical_card_id.tolist()
    assert first == second
    assert len(study.peer_pool(frame(), row(), "drop_nearest_1")) == 2


def test_robust_offset_and_minimum_peer_gate():
    peers = study.peer_pool(frame(), row(), "target_only")
    predicted, _, _ = study.predict(row(), peers, "O1_median_set_offset")
    assert predicted == pytest.approx(2.718281828 ** 2, rel=1e-6)
    predicted, count, status = study.predict(row(), peers.iloc[:2], "C0_set_median")
    assert (predicted, count, status) == (None, 2, "UNAVAILABLE")


def test_price_bands_and_metrics_match_f2_rows():
    assert [study.band(x) for x in (4.99, 5, 10, 25, 50, 100, 250)] == [
        "under_5", "5_to_under_10", "10_to_under_25", "25_to_under_50",
        "50_to_under_100", "100_to_under_250", "250_plus",
    ]
    f2 = pd.read_csv(study.F2)
    model_c = f2[f2.model == "ModelC"]
    loaded = study.load()
    assert len(loaded) == len(model_c) == 4349
    assert loaded.structural_price.tolist() == pytest.approx(model_c.sort_values("canonical_card_id").predicted_price.tolist())
