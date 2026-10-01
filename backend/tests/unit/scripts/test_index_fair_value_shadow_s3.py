from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from backend.scripts import index_fair_value_shadow_anchor_v1 as anchor_mod
from backend.scripts import index_fair_value_shadow_evaluation_v1 as ev
from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod

ROOT = Path(__file__).resolve().parents[4]
EVAL_DATE = date(2026, 10, 10)
CUTOFF = datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)
GENERATED = datetime(2026, 10, 11, 4, 5, tzinfo=timezone.utc)
FPS = {"evidence_snapshot": "a" * 64, "rule_module": "b" * 64}
RULE_MODULE_SHA256 = "f0beb161dbc7e66be90fff6bc4374abffdc4ea1b421d5b1211e9b729a6c0af5a"


def _row(i: int, *, price: str = "100.00", sold_at: str = "2026-10-05", collected: str = "2026-10-06T00:00:00+00:00",
         ingested: str | None = "2026-10-05T12:00:00+00:00", title: str = "Umbreon ex 161/131 NM", **kw):
    base = {"provider_listing_id": i, "provider_card_id": 7, "canonical_card_id": "c1", "title": title, "price": price,
            "currency": "USD", "grader": None, "grade": None, "graded": False, "attribution": "exact",
            "identity_state": "EXACT", "sold_at": sold_at, "ingested_at": ingested, "collected_at": collected,
            "fair_value_signal_eligible": True}
    base.update(kw)
    return base


def _rows(n: int = 12, **kw):
    return [_row(i, price=f"{100 + i}.00", **kw) for i in range(1, n + 1)]


def _build(rows, *, cutoff=CUTOFF, generated=GENERATED, prospective=True, commit="abc1234", replay=False,
           eval_date=EVAL_DATE):
    return anchor_mod.build_anchor_publication(
        canonical_card_id="c1", card_variant_id="v1", card_number="161", evidence_rows=rows,
        evaluation_date=eval_date, information_cutoff=cutoff, generated_at=generated, source_commit=commit,
        input_fingerprints=FPS, prospective=prospective, replay=replay)


# ------------------------------------------------------------------ frozen rule + contract
def test_frozen_rule_module_is_unchanged_since_fv_s2():
    data = (ROOT / "backend/scripts/index_fair_value_sold_clearing_anchor.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == RULE_MODULE_SHA256, (
        "FV-S2 rule changed: create a NEW rule version instead of editing V1 after prospective observation")
    assert anchor_mod.RULE_VERSION == "EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1"


def test_preregistration_artifact_matches_the_code_contract_and_pins_the_rule():
    path = ROOT / "docs/research/index_fair_value/fv_s3/preregistration_v1.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["preregistration"] == ev.PREREGISTRATION
    assert artifact["frozen_rule_module_sha256"] == RULE_MODULE_SHA256
    assert artifact["first_prospective_publication_exists_at_freeze"] is False
    assert artifact["preregistration_sha256"] == hashlib.sha256(
        json.dumps(ev.PREREGISTRATION, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ anchor publication
def test_publication_has_every_required_field_and_is_deterministic():
    rows = _rows()
    pub = _build(rows)
    for field in ("publication_id", "canonical_card_id", "card_variant_id", "rule_version", "evaluation_date",
                  "information_cutoff", "evidence_cutoff", "selected_window_days", "eligible_comp_count",
                  "sold_at_min", "sold_at_max", "collected_at_max", "ingested_at_max", "median", "q1", "q3", "iqr",
                  "mad", "distinct_transaction_days", "evidence_fingerprint", "membership_fingerprint", "members",
                  "exclusion_counts", "evidence_status", "input_fingerprints", "generated_at", "source_commit",
                  "enrichment_policy", "content_fingerprint"):
        assert field in pub, field
    assert pub["status"] == "ANCHORED" and pub["eligible_comp_count"] == 12
    assert pub["evidence_status"] == "PROSPECTIVE_AS_KNOWN_AT_CUTOFF"
    assert pub["enrichment_policy"] == "FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY"
    assert len(pub["members"]) == 12 and pub["median"] == "106.5000"
    again = _build(list(reversed(rows)))
    assert again == pub
    later = _build(rows, generated=GENERATED + timedelta(hours=3), commit="def5678")
    assert (later["content_fingerprint"], later["publication_id"]) == (pub["content_fingerprint"], pub["publication_id"])
    assert later["generated_at"] != pub["generated_at"] and later["source_commit"] != pub["source_commit"]


def test_later_ingested_evidence_cannot_leak_into_an_earlier_publication():
    early_cutoff = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
    known = _rows(10, collected="2026-10-06T00:00:00+00:00")
    # An OLD sale (sold_at inside every window) that we only collected after the cutoff.
    leak = _row(99, price="1.00", sold_at="2026-10-04", collected="2026-10-09T00:00:00+00:00",
                ingested="2026-10-09T00:00:00+00:00")
    # An old sale we collected early but that the provider only ingested after the cutoff.
    provider_late = _row(98, price="1.00", sold_at="2026-10-03", collected="2026-10-07T00:00:00+00:00",
                         ingested="2026-10-09T00:00:00+00:00")
    early_date = date(2026, 10, 8)
    pub = _build(known + [leak, provider_late], cutoff=early_cutoff, generated=early_cutoff + timedelta(minutes=5),
                 eval_date=early_date)
    assert 99 not in [m["provider_listing_id"] for m in pub["members"]]
    assert 98 not in [m["provider_listing_id"] for m in pub["members"]]
    assert pub["exclusion_counts"]["NOT_COLLECTED_AT_CUTOFF"] == 1
    assert pub["exclusion_counts"]["NOT_INGESTED_BY_PROVIDER_AT_CUTOFF"] == 1
    assert pub["median"] == _build(known, cutoff=early_cutoff, generated=early_cutoff + timedelta(minutes=5),
                                    eval_date=early_date)["median"]
    # The same evidence under a later cutoff legitimately sees it: a different, separately keyed publication.
    late = _build(known + [leak, provider_late], eval_date=early_date, cutoff=datetime(2026, 10, 12, tzinfo=timezone.utc),
                  generated=datetime(2026, 10, 12, 1, tzinfo=timezone.utc))
    assert late["membership_fingerprint"] != pub["membership_fingerprint"]
    assert late["publication_id"] != pub["publication_id"]


@pytest.mark.parametrize("collected", [None, "", "not-a-date"])
def test_missing_or_unparseable_availability_fails_closed(collected):
    rows = _rows(10) + [_row(50, collected=collected)]
    pub = _build(rows)
    assert pub["exclusion_counts"]["UNPARSEABLE_AVAILABILITY_TIMESTAMP"] == 1
    assert 50 not in [m["provider_listing_id"] for m in pub["members"]]


def test_sold_at_alone_never_qualifies_a_transaction():
    cutoff = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)
    rows = _rows(12, collected="2026-10-08T00:00:00+00:00")  # sold long ago, collected after the cutoff
    pub = _build(rows, cutoff=cutoff, generated=cutoff + timedelta(minutes=1), eval_date=date(2026, 10, 7))
    assert pub["status"] == "INSUFFICIENT_COMPS" and pub["members"] == [] and pub["median"] is None
    assert pub["eligible_comp_count"] == 0 and pub["exclusion_counts"]["NOT_COLLECTED_AT_CUTOFF"] == 12


def test_insufficient_publication_is_still_recorded():
    pub = _build(_rows(9))
    assert pub["status"] == "INSUFFICIENT_COMPS" and pub["selected_window_days"] is None
    assert pub["eligible_counts_by_window"]["180"] == 9


def test_prospective_timing_guards():
    with pytest.raises(anchor_mod.ShadowAnchorError, match="before its information cutoff"):
        _build(_rows(), generated=CUTOFF - timedelta(seconds=1))
    with pytest.raises(anchor_mod.ShadowAnchorError, match="precedes the start"):
        _build(_rows(), cutoff=datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc), generated=GENERATED)
    with pytest.raises(anchor_mod.ShadowAnchorError, match="timezone-aware"):
        _build(_rows(), cutoff=datetime(2026, 10, 11, 4, 0))
    with pytest.raises(anchor_mod.ShadowAnchorError, match="source_commit"):
        _build(_rows(), commit="not-a-sha!")


def test_as_known_replay_uses_the_availability_gate_but_is_never_labelled_prospective():
    cutoff = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)
    rows = _rows(12, collected="2026-10-08T00:00:00+00:00")
    replay = _build(rows, cutoff=cutoff, generated=GENERATED, replay=True, eval_date=date(2026, 10, 7))
    assert replay["evidence_status"] == "AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE"
    assert replay["status"] == "INSUFFICIENT_COMPS"  # gate applied exactly as for a prospective run
    assert replay["content_fingerprint"] != _build(rows, cutoff=cutoff, generated=GENERATED,
                                                   eval_date=date(2026, 10, 7))["content_fingerprint"]


def test_retrospective_mode_is_labelled_and_not_called_prospective():
    pub = _build(_rows(), prospective=False)
    assert pub["evidence_status"] == "RETROSPECTIVE_BACKFILLED_EVIDENCE"


def test_frozen_rule_still_applies_inside_the_shadow_builder():
    rows = _rows(10) + [_row(60, title="Umbreon ex 161/131 NM PSA 10", price="5000.00"),
                        _row(61, title="Umbreon ex 161/131 LP", price="5.00"),
                        _row(62, graded=True, grader="PSA", grade="10", price="9000.00")]
    pub = _build(rows)
    assert pub["eligible_comp_count"] == 10
    assert {"GRADER_OR_GRADE_EVIDENCE", "WORSE_OR_CONFLICTING_CONDITION", "GRADED_FLAG"} <= set(pub["exclusion_counts"])


# ------------------------------------------------------------------ comparison-price boundary
def test_anchor_builder_has_no_comparison_price_parameter_and_refuses_leaky_inputs():
    params = set(inspect.signature(anchor_mod.build_anchor_publication).parameters)
    assert not any(any(t in p for t in ("price", "market", "comparison", "target", "outcome")) for p in params)
    for key in ("market_price_usd", "target_nm_market_price", "tcgplayer_price", "comparison_price", "realized_error"):
        with pytest.raises(anchor_mod.ShadowAnchorError, match="LEAKAGE_GUARD"):
            _build(_rows() + [_row(77, **{key: 123.0})])
    with pytest.raises(anchor_mod.ShadowAnchorError, match="LEAKAGE_GUARD"):
        anchor_mod.build_anchor_publication(
            canonical_card_id="c1", card_variant_id="v1", card_number="161", evidence_rows=_rows(),
            evaluation_date=EVAL_DATE, information_cutoff=CUTOFF, generated_at=GENERATED, source_commit="abc1234",
            input_fingerprints={"market_price_usd": "1"})
    _build(_rows())  # DB column fair_value_signal_eligible etc. must remain acceptable


def test_anchor_module_cannot_import_or_name_the_evaluation_side():
    source = (ROOT / "backend/scripts/index_fair_value_shadow_anchor_v1.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {node.module or ""} | {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not any("evaluation" in m or "ledger" in m or "components" in m for m in imported), imported
    assert "index_fair_value_shadow_evaluation" not in source


def test_anchor_is_independent_of_any_downstream_market_data():
    rows = _rows()
    assert _build(rows) == _build(copy.deepcopy(rows))
    # Evaluation inputs live on a different code path and never reach the builder.
    pub = _build(rows)
    ev.build_evaluation_outcome(pub, {"horizon_days": 0, "comparison_date": "2026-10-10", "market_price_usd": 9999.0})
    assert _build(rows)["content_fingerprint"] == pub["content_fingerprint"]


# ------------------------------------------------------------------ components / outcomes
def _deep_freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(v) for v in value)
    return value


def test_components_stay_separate_with_exact_divergences_and_no_blend():
    pub = _build(_rows())
    frozen = _deep_freeze(pub)
    obs = ev.build_component_observation(
        frozen, market={"market_price_usd": 150.0, "market_price_date": "2026-10-10"},
        structural={"structural_price_usd": 100.0, "source": "frozen"},
        scarcity={"pull_probability": 0.01, "source": "f1"}, appeal={"collector_appeal": 70.0, "source": "v7"})
    assert obs["shadow_status"] == "COMPLETE" and obs["blended_value"] is None
    assert obs["current_tcgplayer_market_price_usd"] == 150.0
    assert obs["explicit_nm_sold_clearing_anchor_v1_usd"] == 106.5 and obs["structural_baseline_usd"] == 100.0
    assert obs["divergence_sold_anchor_minus_current_market"] == {"usd": -43.5, "pct_of_reference": -29.0}
    assert obs["divergence_structural_minus_current_market"]["usd"] == -50.0
    assert obs["divergence_sold_anchor_minus_structural"] == {"usd": 6.5, "pct_of_reference": 6.5}
    assert obs["negative_ln_pull_probability"] == pytest.approx(4.60517, abs=1e-5)
    assert obs["evidence_age_days_since_newest_sale"] == 5 and obs["comp_count"] == 12
    assert "fair_value" not in " ".join(k for k in obs if k != "blended_value").lower().replace("fair_value_signal", "")


@pytest.mark.parametrize("kwargs,status", [
    ({"market": None, "structural": {"structural_price_usd": 1}}, "MARKET_MISSING"),
    ({"market": {"market_price_usd": 1}, "structural": None}, "STRUCTURAL_MISSING"),
])
def test_component_status_for_missing_inputs(kwargs, status):
    obs = ev.build_component_observation(_build(_rows()), scarcity=None, appeal=None, **kwargs)
    assert obs["shadow_status"] == status


def test_component_status_for_insufficient_anchor():
    obs = ev.build_component_observation(_build(_rows(9)), market={"market_price_usd": 5.0},
                                         structural={"structural_price_usd": 4.0}, scarcity=None, appeal=None)
    assert obs["shadow_status"] == "ANCHOR_INSUFFICIENT"
    assert obs["divergence_sold_anchor_minus_current_market"] == {"usd": None, "pct_of_reference": None}


def test_outcome_math_validation_and_publication_immutability():
    pub = _build(_rows())
    before = json.dumps(pub, sort_keys=True)
    out0 = ev.build_evaluation_outcome(pub, {"horizon_days": 0, "comparison_date": "2026-10-10",
                                            "market_price_usd": 150.0, "source": "TCGPlayer"})
    assert out0["abs_error_usd"] == 43.5 and out0["signed_pct_error"] == -29.0 and out0["abs_pct_error"] == 29.0
    out7 = ev.build_evaluation_outcome(
        pub, {"horizon_days": 7, "comparison_date": "2026-10-17", "market_price_usd": 165.0},
        baseline_market_price_usd=150.0, today=date(2026, 10, 20))
    assert out7["forward_market_change_pct"] == 10.0 and out7["divergence_at_publication"] == -0.29
    assert json.dumps(pub, sort_keys=True) == before
    with pytest.raises(ev.EvaluationError, match="evaluation_date \\+ horizon"):
        ev.build_evaluation_outcome(pub, {"horizon_days": 1, "comparison_date": "2026-10-12", "market_price_usd": 1})
    with pytest.raises(ev.EvaluationError, match="future"):
        ev.build_evaluation_outcome(pub, {"horizon_days": 30, "comparison_date": "2026-11-09", "market_price_usd": 1},
                                    today=date(2026, 10, 20))
    with pytest.raises(ev.EvaluationError):
        ev.build_evaluation_outcome(pub, {"horizon_days": 3, "comparison_date": "2026-10-13", "market_price_usd": 1})


# ------------------------------------------------------------------ ledger
def test_ledger_is_append_only_idempotent_and_conflict_safe():
    ledger = ledger_mod.InMemoryShadowLedger()
    pub = _build(_rows())
    assert ledger.append_publication(pub) == "INSERTED"
    retry = _build(_rows(), generated=GENERATED + timedelta(hours=1))
    assert ledger.append_publication(retry) == "IDEMPOTENT_NOOP"
    assert len(ledger.publications()) == 1 and ledger.publications()[0]["generated_at"] == pub["generated_at"]
    different = _build(_rows(11))
    assert different["publication_id"] != pub["publication_id"]
    with pytest.raises(ledger_mod.ShadowLedgerConflict):
        ledger.append_publication(different)  # same key, different content: never an overwrite
    assert not [m for m in dir(ledger) if m.startswith(("update", "delete", "upsert", "remove"))]


def test_outcomes_never_change_anchor_membership_or_estimate():
    ledger = ledger_mod.InMemoryShadowLedger()
    pub = _build(_rows())
    ledger.append_publication(pub)
    snapshot = json.dumps(ledger.get_publication(pub["publication_id"]), sort_keys=True)
    for horizon, date_, price in ((0, "2026-10-10", 80.0), (1, "2026-10-11", 90.0), (7, "2026-10-17", 500.0)):
        outcome = ev.build_evaluation_outcome(pub, {"horizon_days": horizon, "comparison_date": date_, "market_price_usd": price})
        assert ledger.append_outcome(outcome) == "INSERTED"
        assert ledger.append_outcome(outcome) == "IDEMPOTENT_NOOP"
    assert json.dumps(ledger.get_publication(pub["publication_id"]), sort_keys=True) == snapshot
    assert ledger.get_publication(pub["publication_id"])["median"] == "106.5000"
    conflicting = ev.build_evaluation_outcome(pub, {"horizon_days": 0, "comparison_date": "2026-10-10", "market_price_usd": 1.0})
    with pytest.raises(ledger_mod.ShadowLedgerConflict):
        ledger.append_outcome(conflicting)
    with pytest.raises(ledger_mod.ShadowLedgerError):
        ledger.append_outcome({**conflicting, "publication_id": "missing"})


def test_dormant_database_adapter_refuses_every_write():
    class Boom:
        def table(self, name):
            raise AssertionError("database touched")

    adapter = ledger_mod.SupabaseShadowLedger(Boom())
    assert ledger_mod.WRITE_ENABLED is False
    for call in (lambda: adapter.append_publication(_build(_rows())), lambda: adapter.append_outcome({}),
                 lambda: adapter.append_component({})):
        with pytest.raises(ledger_mod.ShadowLedgerDormant):
            call()


# ------------------------------------------------------------------ preregistered metrics
def test_anchor_accuracy_known_values_and_strata():
    rows = [{"anchor_usd": 90.0, "market_price_usd": 100.0}, {"anchor_usd": 220.0, "market_price_usd": 200.0},
            {"anchor_usd": 300.0, "market_price_usd": 400.0}, {"anchor_usd": 24.0, "market_price_usd": 30.0}]
    m = ev.anchor_accuracy(rows)
    assert m["n"] == 4 and m["status"] == "INSUFFICIENT_N"
    assert m["mdape_pct"] == pytest.approx(15.0) and m["mae_usd"] == pytest.approx(34.0)
    assert m["within_10pct"] == 50.0 and m["within_20pct"] == 75.0 and m["within_30pct"] == 100.0
    assert m["spearman"] == pytest.approx(1.0)
    strata = ev.stratified_accuracy(rows, eligible_cards=5)
    assert [strata[k]["n"] for k in ("all", "ge_25", "ge_100", "ge_250")] == [4, 4, 3, 1]
    assert strata["coverage"] == {"anchored_with_market": 4, "eligible_cards": 5}


def test_r2_dollars_formula():
    rows = [{"anchor_usd": a, "market_price_usd": m} for a, m in ((10, 10), (20, 20), (30, 40))]
    expected = 1 - (10 ** 2) / ((10 - 70 / 3) ** 2 + (20 - 70 / 3) ** 2 + (40 - 70 / 3) ** 2)
    assert ev.anchor_accuracy(rows)["r2_dollars"] == pytest.approx(expected, abs=1e-5)


def _forward_rows(n=60, informative=True):
    rows = []
    for i in range(n):
        p0 = 100.0 + i
        d = ((i % 9) - 4) / 20.0
        rows.append({"anchor_usd": p0 * (1 + d), "market_t0_usd": p0,
                     "market_th_usd": p0 * (1 + (0.5 * d if informative else 0.01 * ((i * 7) % 5 - 2))),
                     "cluster": f"set{i % 6}"})
    return rows


def test_forward_diagnostics_are_deterministic_and_do_not_presuppose_a_conclusion():
    rows = _forward_rows()
    a = ev.forward_diagnostics(rows, horizon_days=7)
    assert a == ev.forward_diagnostics(copy.deepcopy(rows), horizon_days=7)
    assert a["status"] == "OK" and a["spearman_divergence_vs_forward_return"] > 0.9
    assert a["ols_slope_forward_return_on_divergence"] == pytest.approx(0.5, abs=1e-6)
    lo, hi = a["ols_slope_bootstrap_95ci"]
    assert lo <= 0.5 <= hi
    assert a["mean_forward_return_by_divergence_tercile"]["highest"] > a["mean_forward_return_by_divergence_tercile"]["lowest"]
    noise = ev.forward_diagnostics(_forward_rows(informative=False), horizon_days=7)
    assert abs(noise["spearman_divergence_vs_forward_return"]) < 0.5  # same code reports "no information" too


def test_forward_diagnostics_label_small_samples_and_skip_inference():
    out = ev.forward_diagnostics(_forward_rows(12), horizon_days=30)
    assert out["status"] == "INSUFFICIENT_N" and out["ols_slope_bootstrap_95ci"] is None
    assert ev.forward_diagnostics([], horizon_days=1)["n"] == 0


# ------------------------------------------------------------------ unapplied migration proposal
PROPOSAL = ROOT / "docs/research/index_fair_value/fv_s3/migration_proposal_unapplied/20261001000000_fair_value_shadow_ledger_v1.sql.proposed"


NEWLINE_CLOSE = chr(10) + ");"


def _ddl_columns(sql: str, table: str) -> set[str]:
    sql = sql.replace(chr(13) + chr(10), chr(10))
    body = sql.split(f"CREATE TABLE public.{table} (", 1)[1].split(NEWLINE_CLOSE, 1)[0]
    cols = set()
    for line in body.splitlines():
        m = __import__("re").match(r"^  ([a-z_0-9]+) [a-z]", line)
        if m and m.group(1) not in {"primary", "unique", "check", "foreign"}:
            cols.add(m.group(1))
    return cols


def test_ledger_migration_is_proposed_only_and_not_in_any_migration_directory():
    assert PROPOSAL.exists()
    for directory in ("supabase/migrations", "backend/db/migrations"):
        assert not [p for p in (ROOT / directory).glob("*") if "fair_value_shadow" in p.name]
    sql = PROPOSAL.read_text(encoding="utf-8")
    assert sql.lstrip().startswith("-- PROPOSED / NOT APPLIED")
    assert "GRANT SELECT, INSERT ON" in sql and "GRANT SELECT, INSERT, UPDATE" not in sql
    assert "BEFORE UPDATE OR DELETE" in sql and "BEFORE TRUNCATE" in sql and "ENABLE ROW LEVEL SECURITY" in sql
    assert "UNIQUE (rule_version, canonical_card_id, evaluation_date, information_cutoff)" in sql
    assert "CHECK (blended_value IS NULL)" in sql


def test_ledger_columns_cover_everything_the_python_records_carry():
    sql = PROPOSAL.read_text(encoding="utf-8")
    pub = _build(_rows())
    publication_cols = _ddl_columns(sql, "fair_value_shadow_anchor_publications_v1")
    assert set(pub) - {"members"} <= publication_cols, set(pub) - {"members"} - publication_cols
    assert set(pub["members"][0]) <= _ddl_columns(sql, "fair_value_shadow_anchor_members_v1") | {"publication_id"}
    obs = ev.build_component_observation(pub, market={"market_price_usd": 1.0}, structural={"structural_price_usd": 1.0},
                                         scarcity=None, appeal=None)
    assert set(obs) <= _ddl_columns(sql, "fair_value_shadow_component_observations_v1"), (
        set(obs) - _ddl_columns(sql, "fair_value_shadow_component_observations_v1"))
    out = ev.build_evaluation_outcome(pub, {"horizon_days": 0, "comparison_date": "2026-10-10", "market_price_usd": 1.0})
    assert set(out) <= _ddl_columns(sql, "fair_value_shadow_evaluation_outcomes_v1")
    # The anchor table has no comparison-price column at all.
    assert not [c for c in publication_cols if "market" in c or "comparison" in c or "outcome" in c]
