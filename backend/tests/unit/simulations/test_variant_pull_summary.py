from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.simulations.variant_pull_summary import VariantPullSummaryRecorder


def _source():
    return pd.DataFrame([{
        "card_id": "card-1", "card_variant_id": "base-1", "condition_id": "nm",
        "printing_type": "non-holo", "price_source": "base-source",
        "captured_at": "2026-08-01T00:00:00Z", "Price ($)": 0.1,
        "reverse_variant_id": "reverse-1", "reverse_condition_id": "nm",
        "reverse_printing_type": "reverse-holo", "reverse_price_source": "reverse-source",
        "reverse_captured_at": "2026-08-02T00:00:00Z", "Reverse Variant Price ($)": 0.25,
        "Card Name": "Common One", "Card Number": "001", "Rarity": "Common",
    }])


def test_base_and_reverse_sampling_entities_publish_distinct_exact_variants_and_provenance():
    recorder = VariantPullSummaryRecorder(_source())
    base = recorder.register_row(source_row_index=0, price_column="Price ($)", price=0.1)
    reverse = recorder.register_row(source_row_index=0, price_column="Reverse Variant Price ($)", price=0.25)
    recorder.open_pack(); recorder.add([base, reverse, reverse]); recorder.close_pack()
    rows = {row["cardVariantId"]: row for row in recorder.finalize()}
    assert rows["base-1"]["pullCount"] == 1
    assert rows["reverse-1"]["pullCount"] == 2
    assert rows["reverse-1"]["packPresenceCount"] == 1
    assert rows["reverse-1"]["modeledProbability"] == pytest.approx(1.0)
    assert rows["reverse-1"]["priceSource"] == "reverse-source"
    assert rows["reverse-1"]["priceCapturedAt"] == "2026-08-02T00:00:00Z"


def test_registered_zero_draw_variant_is_explicitly_insufficient_not_probability_zero():
    recorder = VariantPullSummaryRecorder(_source())
    recorder.register_row(source_row_index=0, price_column="Reverse Variant Price ($)", price=0.25)
    recorder.open_pack(); recorder.close_pack()
    row = recorder.finalize()[0]
    assert row["status"] == "insufficient_observed_pulls"
    assert row["modeledProbability"] is None
    assert row["effectivePullRate"] is None


def test_summary_observer_does_not_consume_random_numbers():
    baseline = np.random.default_rng(42)
    observed = np.random.default_rng(42)
    recorder = VariantPullSummaryRecorder(_source())
    entity = recorder.register_row(source_row_index=0, price_column="Price ($)", price=0.1)
    expected = []
    actual = []
    for _ in range(100):
        expected.append(float(baseline.random()))
        recorder.open_pack()
        actual.append(float(observed.random()))
        recorder.add(entity)
        recorder.close_pack()
    assert actual == expected


def test_summary_observer_does_not_perturb_authoritative_v2_simulation():
    from backend.simulations.monteCarloSimV2 import make_simulate_pack_fn_v2
    from backend.tests.unit.research.test_ev_representativeness_contribution import _ToyConfig, _tiny_pool

    def build(observer=None):
        commons = _tiny_pool(["C1", "C2", "C3"], [0.05, 0.10, 0.15], "Common", 0)
        uncommons = _tiny_pool(["U1", "U2"], [0.20, 0.25], "Uncommon", 10)
        rares = _tiny_pool(["R1", "R2"], [0.50, 0.75], "Rare", 20)
        hits = _tiny_pool(["H1", "H2"], [40.0, 90.0], "Double Rare", 30)
        reverse = _tiny_pool(["C1", "C2"], [0.05, 0.10], "Common", 0)
        source = pd.concat([commons, uncommons, rares, hits], ignore_index=True)
        for i, row in source.iterrows():
            source.at[i, "card_id"] = f"card-{i}"
            source.at[i, "card_variant_id"] = f"base-{i}"
            source.at[i, "reverse_variant_id"] = f"reverse-{i}"
        recorder = VariantPullSummaryRecorder(source) if observer else None
        fn = make_simulate_pack_fn_v2(
            common_cards=commons, uncommon_cards=uncommons, rare_cards=rares,
            hit_cards=hits, reverse_pool=reverse, slots_per_rarity=_ToyConfig.SLOTS_PER_RARITY,
            config=_ToyConfig(), df=source, rarity_pull_counts=defaultdict(int),
            rarity_value_totals=defaultdict(float), rng=np.random.default_rng(20260827),
            variant_summary_recorder=recorder,
        )
        return fn, recorder

    baseline_fn, _ = build(False)
    observed_fn, recorder = build(True)
    baseline = [float(baseline_fn()) for _ in range(2000)]
    observed = [float(observed_fn()) for _ in range(2000)]
    assert observed == baseline
    assert recorder.finalize()
