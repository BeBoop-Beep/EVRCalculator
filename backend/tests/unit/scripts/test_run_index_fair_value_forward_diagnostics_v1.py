from __future__ import annotations

from backend.scripts import run_index_fair_value_forward_diagnostics_v1 as runner


def test_assemble_forward_rows_uses_frozen_root_set_clusters_and_excludes_insufficient():
    panel = {
        "rows": [
            {
                "canonical_card_id": "c1",
                "card_variant_id": "v1",
                "root_set_id": "set-a",
                "set_name": "A",
                "era": "Era",
                "price_band": "25_to_under_50",
            },
            {
                "canonical_card_id": "c2",
                "card_variant_id": "v2",
                "root_set_id": "set-b",
                "set_name": "B",
                "era": "Era",
                "price_band": "under_5",
            },
        ]
    }
    publications = [
        {
            "publication_id": "p1",
            "canonical_card_id": "c1",
            "card_variant_id": "v1",
            "status": "ANCHORED",
            "median": "120",
        },
        {
            "publication_id": "p2",
            "canonical_card_id": "c2",
            "card_variant_id": "v2",
            "status": "INSUFFICIENT_COMPS",
            "median": None,
        },
    ]
    outcomes = [
        {
            "publication_id": "p1",
            "horizon_days": 0,
            "comparison_market_price_usd": 100,
            "outcome_status": "COMPLETE",
        },
        {
            "publication_id": "p1",
            "horizon_days": 1,
            "comparison_market_price_usd": 110,
            "outcome_status": "COMPLETE",
        },
        {
            "publication_id": "p2",
            "horizon_days": 0,
            "comparison_market_price_usd": 2,
            "outcome_status": "ANCHOR_INSUFFICIENT",
        },
        {
            "publication_id": "p2",
            "horizon_days": 1,
            "comparison_market_price_usd": 2.1,
            "outcome_status": "ANCHOR_INSUFFICIENT",
        },
    ]
    rows, coverage = runner.assemble_forward_rows(
        panel=panel,
        publications=publications,
        outcomes=outcomes,
        horizon_days=1,
    )
    assert rows == [{
        "publication_id": "p1",
        "canonical_card_id": "c1",
        "anchor_usd": "120",
        "market_t0_usd": 100,
        "market_th_usd": 110,
        "cluster": "set-a",
        "root_set_id": "set-a",
        "set_name": "A",
        "era": "Era",
        "price_band": "25_to_under_50",
    }]
    assert coverage["usable_rows"] == 1
    assert coverage["root_set_clusters"] == 1
    assert coverage["excluded_reasons"] == {
        "ANCHOR_INSUFFICIENT": 1,
        "USABLE": 1,
    }


def test_stratified_forward_diagnostics_uses_frozen_market_t0_floors():
    rows = [
        {"anchor_usd": 11, "market_t0_usd": 10, "market_th_usd": 10.5, "cluster": "a"},
        {"anchor_usd": 30, "market_t0_usd": 25, "market_th_usd": 26, "cluster": "b"},
        {"anchor_usd": 110, "market_t0_usd": 100, "market_th_usd": 102, "cluster": "c"},
        {"anchor_usd": 275, "market_t0_usd": 250, "market_th_usd": 255, "cluster": "d"},
    ]
    out = runner.stratified_forward_diagnostics(rows, 1)
    assert out["all"]["n"] == 4
    assert out["ge_25"]["n"] == 3
    assert out["ge_100"]["n"] == 2
    assert out["ge_250"]["n"] == 1
    assert all(v["horizon_days"] == 1 for v in out.values())
