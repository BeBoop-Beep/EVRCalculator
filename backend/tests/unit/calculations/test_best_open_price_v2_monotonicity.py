"""Best-Open Price V2 - Bucket 1 monotonicity regression fixtures.

Every fixture here runs the REAL canonical scorer
(``PreparedCanonicalCandidate.score_candidate`` -> ``PreparedFinancialRipDistribution.score``
-> Financial V4 projection -> Overall V12) and the REAL comparators
(``PreparedCanonicalCandidate.compare``).  Only the outcome distributions are
synthetic (tiny, hand-described multisets), and the benchmark rows are plain
mappings.  ``min_simulation_count=1`` lets a 100-outcome vector reach the
scorer; nothing else about the scorer is relaxed.

The numbers asserted below were produced by that scorer.  They are permanent
proof that the Best-Open winner predicate is NOT monotone in acquisition price
in general, which is why an unrestricted binary search is not certified.

See ``docs/research/BEST_OPEN_PRICE_V2_MONOTONICITY_CERTIFICATION.md``.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.calculations.evr.best_open_price import (
    COMPARISON_AUTHORITY_FINANCIAL_V4 as FIN,
    COMPARISON_AUTHORITY_OVERALL_V12 as V12,
    PreparedCanonicalCandidate,
    quantity_price_interval_cents,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.scripts.research_best_open_price_v2_monotonicity import (
    NON_LR_COMPONENTS,
    analyze_rows,
    benchmark_row,
    branch_and_bound_highest_win,
    bound_prunes,
    interval_upper_bound,
    is_down_closed,
    loss_resilience_upper_bound,
    q_level_summary,
    run_pattern,
    score_with_detail,
    sweep_interval,
)


# ---------------------------------------------------------------------------
# Synthetic distribution builders (real scorer, tiny controlled inputs)
# ---------------------------------------------------------------------------

def candidate(multiset, *, quantity=1, product_id="cand", collector=50.0, accessibility=0.05, target=100.0):
    """A canonical candidate over ``[(value, count), ...]`` outcomes."""
    values = np.concatenate([np.full(count, value, dtype=float) for value, count in multiset])
    prepared = PreparedFinancialRipDistribution.prepare(values)
    return PreparedCanonicalCandidate(
        product_id, quantity, prepared, collector, accessibility, target, min_simulation_count=1,
    )


# 100 outcomes: four losing packs (1,2,3,4), 95 packs worth 10, one jackpot 12.
REBOUND = [(1.0, 1), (2.0, 1), (3.0, 1), (4.0, 1), (10.0, 95), (12.0, 1)]
# 100 identical packs: every cost up to 0.03 leaves every Financial/Overall input saturated.
PLATEAU = [(10.0, 100)]


def flags(cand, low, high, bench, authority):
    return [
        bool(cand.compare(cand.score_candidate(p), bench, authority=authority))
        for p in range(low, high + 1)
    ]


def winners(cand, low, high, bench, authority):
    return [
        p for p in range(low, high + 1)
        if cand.compare(cand.score_candidate(p), bench, authority=authority)
    ]


def fin_bench(tau, *, product_id="zzz"):
    """Financial comparator benchmark: only score and id are read."""
    return benchmark_row(product_id, financial=tau, overall=0.0, recover=1.0, capital=0.0, target=100.0)


# ---------------------------------------------------------------------------
# 1A - Loss Resilience is the one component that can move upward with cost
# ---------------------------------------------------------------------------

def test_loss_resilience_jumps_up_when_cost_crosses_an_outcome_value():
    cand = candidate(REBOUND)
    before_record, before = score_with_detail(cand, 400)   # C = 4.00 : the 4.0 pack still recovers cost
    after_record, after = score_with_detail(cand, 401)     # C = 4.01 : the 4.0 pack is now a loss
    # A tie at exactly the cost counts as a win (P(X >= C)).
    assert before_record["chanceToRecoverCapital"] == 0.97
    assert after_record["chanceToRecoverCapital"] == 0.96
    assert before["avgRetention"] == 0.5 and after["avgRetention"] == 0.6234414
    assert before["softShare"] == 0.66666667 and after["softShare"] == 0.5
    # Loss Resilience component RISES 55.0 -> 58.6409 as price rises one cent.
    assert before["lrScore"] == 55.0 and after["lrScore"] == 58.6409
    # Every other component is non-increasing, and the total score rises.
    for key in NON_LR_COMPONENTS:
        assert after["components"][key] <= before["components"][key]
    assert before_record["financialRipV4Score"] == 78.676
    assert after_record["financialRipV4Score"] == 79.2028


def test_no_losing_runs_boundary_is_a_downward_step_only():
    cand = candidate(REBOUND)
    _r100, at_min = score_with_detail(cand, 100)   # C = 1.00: nobody loses
    _r101, above_min = score_with_detail(cand, 101)
    assert at_min["noLosingRuns"] is True and at_min["lrScore"] == 100.0
    assert above_min["noLosingRuns"] is False and above_min["lrScore"] == 99.3069


def test_hard_loss_crossing_lowers_soft_share_and_raises_hard_probability():
    cand = candidate(REBOUND)
    _r, at_two = score_with_detail(cand, 200)      # C = 2.00: value 1.0 is exactly C/2 (soft)
    _r, above = score_with_detail(cand, 201)       # C = 2.01: 1.0 < 1.005 (now hard)
    assert at_two["softShare"] == 1.0 and above["softShare"] == 0.5
    assert at_two["hardLoss"] == 0.0 and above["hardLoss"] == 0.01


def test_true_win_and_non_loss_resilience_components_never_increase_with_cost():
    rng = np.random.default_rng(20260919)
    for _ in range(6):
        n = int(rng.choice([100, 200, 400]))
        values = np.round(rng.lognormal(mean=rng.uniform(-1, 1.5), sigma=rng.uniform(0.3, 1.6), size=n) * 2.0, 2)
        cand = candidate([(float(v), 1) for v in values])
        previous = None
        for price in range(1, 700):
            record, detail = score_with_detail(cand, price)
            if previous is not None:
                assert record["chanceToRecoverCapital"] <= previous[0]["chanceToRecoverCapital"]
                for key in NON_LR_COMPONENTS:
                    assert detail["components"][key] <= previous[1]["components"][key], key
            previous = (record, detail)


# ---------------------------------------------------------------------------
# 1B - Financial V4 is NOT monotone in price; it IS strictly decreasing where P(win) <= 1/2
# ---------------------------------------------------------------------------

def test_financial_v4_score_increases_with_price_counterexample():
    cand = candidate(REBOUND)
    scores = {p: cand.score_candidate(p)["financialRipV4Score"] for p in (200, 201, 300, 301, 400, 401)}
    assert scores == {200: 85.8908, 201: 86.1992, 300: 80.489, 301: 82.9319, 400: 78.676, 401: 79.2028}
    # And the Overall V12 headline follows Financial V4 upward as well.
    assert cand.score_candidate(400)["overallRipV12Score"] == 76.5075
    assert cand.score_candidate(401)["overallRipV12Score"] == 76.9606


def test_financial_v4_never_rises_while_true_win_probability_is_at_most_one_half():
    """Theorem A, checked against the real scorer.

    At an outcome crossing the true-win term loses at least 0.25 * (100/0.15) * m/n
    points while Loss Resilience gains at most 0.15 * 100 * m/(k+m); with
    P(win) <= 1/2 we have k+m >= n/2, so the net move is strictly negative.
    """
    rng = np.random.default_rng(20260919)
    region_pairs = outside_pairs = outside_up = 0
    for _ in range(12):
        n = int(rng.choice([100, 200, 400]))
        values = np.round(rng.lognormal(mean=rng.uniform(-1, 1.5), sigma=rng.uniform(0.3, 1.6), size=n) * 2.0, 2)
        cand = candidate([(float(v), 1) for v in values])
        previous = None
        for price in range(1, 900):
            record = cand.score_candidate(price)
            if previous is not None:
                rose = record["financialRipV4Score"] > previous["financialRipV4Score"]
                if previous["chanceToRecoverCapital"] <= 0.5:
                    region_pairs += 1
                    assert not rose, (price, previous, record)
                else:
                    outside_pairs += 1
                    outside_up += int(rose)
            previous = record
    assert region_pairs > 1000
    # The region restriction is necessary: outside it the score does rise.
    assert outside_up > 0


# ---------------------------------------------------------------------------
# 1C / 1D - Winner-predicate patterns (Financial V4 comparator: score, then id)
# ---------------------------------------------------------------------------

def test_financial_control_pattern_is_down_closed_win_then_loss():
    cand = candidate(REBOUND)
    pattern = flags(cand, 401, 519, fin_bench(76.0), FIN)
    assert run_pattern(pattern) == "W L"
    assert is_down_closed(pattern)


def test_financial_one_cent_winning_island_loss_win_loss():
    cand = candidate(REBOUND)
    bench = fin_bench(82.9319)
    assert winners(cand, 260, 400, bench, FIN) == [301]
    assert run_pattern(flags(cand, 260, 400, bench, FIN)) == "L W L"
    # The loss immediately below the island scores 80.489 < 82.9319.
    assert cand.score_candidate(300)["financialRipV4Score"] == 80.489
    assert cand.score_candidate(302)["financialRipV4Score"] == 82.8752


def test_financial_win_loss_win_loss_separated_winning_ranges():
    cand = candidate(REBOUND)
    bench = fin_bench(82.9319)
    pattern = flags(cand, 250, 400, bench, FIN)
    assert run_pattern(pattern) == "W L W L"
    assert not is_down_closed(pattern)
    won = winners(cand, 250, 400, bench, FIN)
    assert won[0] == 250 and 301 in won and 259 not in won and 300 not in won


def test_financial_win_loss_win_rebound():
    cand = candidate(REBOUND)
    pattern = flags(cand, 250, 305, fin_bench(82.7), FIN)
    assert run_pattern(pattern) == "W L W"
    assert not is_down_closed(pattern)


def test_score_step_up_does_not_always_break_the_winner_predicate():
    """An upward score step is necessary but not sufficient for a violation."""
    cand = candidate(REBOUND)
    assert cand.score_candidate(301)["financialRipV4Score"] > cand.score_candidate(300)["financialRipV4Score"]
    pattern = flags(cand, 250, 400, fin_bench(70.0), FIN)
    assert run_pattern(pattern) == "W"


# ---------------------------------------------------------------------------
# 1C / 1D - Overall V12: tie-break driven higher-price win (capital closeness)
# ---------------------------------------------------------------------------

def _plateau_bench(*, recover=1.0, capital=0.025, product_id="zzz"):
    return benchmark_row(product_id, financial=100.0, overall=94.8462, recover=recover,
                         capital=capital, target=100.0)


def test_overall_v12_tie_break_makes_only_the_highest_plateau_price_win():
    cand = candidate(PLATEAU)
    records = [cand.score_candidate(p) for p in (1, 2, 3, 4)]
    # Prices 1..3 have IDENTICAL headline: Financial 100.0, Overall 94.8462, P(win) 1.0.
    assert {(r["financialRipV4Score"], r["overallRipV12Score"], r["chanceToRecoverCapital"])
            for r in records[:3]} == {(100.0, 94.8462, 1.0)}
    assert records[3]["financialRipV4Score"] == 99.9997
    bench = _plateau_bench()
    # Overall V12: capital closeness to target decides the tie, and a HIGHER price
    # commits more capital, so it wins where a lower price with the same headline loses.
    assert flags(cand, 1, 4, bench, V12) == [False, False, True, False]
    # Financial V4 (score, then product id) treats the three plateau prices identically.
    assert flags(cand, 1, 4, bench, FIN) == [True, True, True, False]


def test_financial_monotone_but_overall_v12_not():
    cand = candidate(PLATEAU)
    bench = _plateau_bench()
    financial = flags(cand, 1, 12, bench, FIN)
    overall = flags(cand, 1, 12, bench, V12)
    assert run_pattern(financial) == "W L" and is_down_closed(financial)
    assert run_pattern(overall) == "L W L" and not is_down_closed(overall)


def test_overall_v12_verdict_changes_while_every_score_is_unchanged():
    cand = candidate(PLATEAU)
    rows = sweep_interval(cand, 1, 8, financial_benchmark=fin_bench(100.0),
                          overall_benchmark=_plateau_bench())
    analysis = analyze_rows(rows, "overall")
    assert analysis["pattern"] == "L W L"
    assert analysis["oneCentIslands"] == 1 and analysis["oneCentIslandPrices"] == [3]
    assert analysis["winnerChangesWithUnchangedScore"] == 1
    assert analysis["lossToWinTransitions"] == 1


def test_overall_v12_product_id_breaks_a_full_tie_the_same_way_at_every_price():
    cand = candidate(PLATEAU)
    # bench sorts BEFORE the candidate and matches its capital exactly: the id decides,
    # and it decides identically for every price with equal capital closeness... but a
    # lower price is farther from target, so it can only lose.
    bench = _plateau_bench(product_id="aaa", capital=0.03)
    assert flags(cand, 1, 3, bench, V12) == [False, False, False]


def test_financial_v4_id_tie_break_is_price_independent():
    cand = candidate(PLATEAU)
    low_id = benchmark_row("aaa", financial=100.0, overall=0.0, recover=1.0, capital=0.0, target=100.0)
    high_id = benchmark_row("zzz", financial=100.0, overall=0.0, recover=1.0, capital=0.0, target=100.0)
    assert flags(cand, 1, 3, low_id, FIN) == [False, False, False]
    assert flags(cand, 1, 3, high_id, FIN) == [True, True, True]


# ---------------------------------------------------------------------------
# Authority disagreement on the same distribution
# ---------------------------------------------------------------------------

def test_overall_v12_can_be_monotone_where_financial_v4_is_not():
    cand = candidate(REBOUND)
    financial = flags(cand, 260, 400, fin_bench(82.9319), FIN)
    low_overall = benchmark_row("zzz", financial=50.0, overall=70.0, recover=0.5, capital=0.0, target=100.0)
    overall = flags(cand, 260, 400, low_overall, V12)
    assert run_pattern(financial) == "L W L" and not is_down_closed(financial)
    assert run_pattern(overall) == "W" and is_down_closed(overall)


# ---------------------------------------------------------------------------
# Quantity boundary (q -> q+1): distributions are independent per q
# ---------------------------------------------------------------------------

def test_quantity_boundary_can_reverse_the_predicate():
    budget_cents = 1000
    low3, high3 = quantity_price_interval_cents(budget_cents, 3)
    low2, high2 = quantity_price_interval_cents(budget_cents, 2)
    assert (low3, high3, low2, high2) == (251, 333, 334, 500)
    poor_q3 = candidate([(0.5, 100)], quantity=3)      # q=3 pack basket is a poor outcome vector
    good_q2 = candidate([(10.0, 100)], quantity=2)     # q=2 pack basket is a strong one
    bench = fin_bench(50.0)
    rows = (
        sweep_interval(poor_q3, low3, high3, financial_benchmark=bench, overall_benchmark=bench)
        + sweep_interval(good_q2, low2, high2, financial_benchmark=bench, overall_benchmark=bench)
    )
    analysis = analyze_rows(rows, "financial")
    # Ascending price: every q=3 cent loses, every q=2 cent wins - a higher price wins where the lower loses.
    assert analysis["pattern"] == "L W" and analysis["downClosed"] is False
    assert analysis["quantityBoundaryLossToWin"] == 1
    assert analysis["lossToWinTransitions"] == 1


def test_q_level_pattern_has_no_implication_between_quantities():
    """No theorem links q1 < q < q2: fixtures may fail, win, fail, win in turn."""
    summary = q_level_summary({1: False, 2: True, 3: False, 4: True, 5: True})
    assert summary["pattern"] == "L W L W"
    assert summary["firstWinnableQuantity"] == 2
    assert summary["holesAfterFirstWinnable"] == [3]
    assert summary["alternations"] == 3


# ---------------------------------------------------------------------------
# 1G - conservative bound + branch and bound: zero false prunes
# ---------------------------------------------------------------------------

def test_naive_bound_at_the_low_price_would_falsely_prune_the_island_but_the_real_bound_does_not():
    cand = candidate(REBOUND)
    bench = fin_bench(82.9319)
    naive_upper = cand.score_candidate(300)["financialRipV4Score"]      # score at the LOW end of [300, 301]
    assert naive_upper < 82.9319                                          # would prune ...
    assert cand.score_candidate(301)["financialRipV4Score"] == 82.9319    # ... a real winning cent
    bound = interval_upper_bound(cand, 300, 301)
    assert bound["financialUb"] >= 82.9319
    assert not bound_prunes(cand, bound, bench, "financial")


def test_loss_resilience_bound_dominates_every_cent_in_the_interval():
    cand = candidate(REBOUND)
    for low, high in ((100, 120), (190, 215), (295, 305), (395, 410), (1, 600)):
        bound = loss_resilience_upper_bound(cand, low, high)
        actual = max(score_with_detail(cand, p)[1]["lrScore"] for p in range(low, high + 1))
        assert bound >= actual


def test_upper_bound_dominates_exact_scores_and_branch_and_bound_matches_exhaustive_search():
    rng = np.random.default_rng(7)
    checked = pruned = 0
    for trial in range(8):
        n = int(rng.choice([100, 200, 400]))
        values = np.round(rng.lognormal(mean=rng.uniform(-0.5, 1.5), sigma=rng.uniform(0.3, 1.4), size=n) * 2.0, 2)
        cand = candidate([(float(v), 1) for v in values])
        span = 900
        scores = {p: cand.score_candidate(p) for p in range(1, span + 1)}
        finals = {p: scores[p]["financialRipV4Score"] for p in scores}
        for _ in range(12):
            low = int(rng.integers(1, span - 50))
            high = int(low + rng.integers(2, 48))
            bound = interval_upper_bound(cand, low, high)
            assert bound["financialUb"] >= max(finals[p] for p in range(low, high + 1))
            assert bound["overallUb"] >= max(scores[p]["overallRipV12Score"] for p in range(low, high + 1))
            checked += 1
        tau = float(np.quantile(list(finals.values()), rng.uniform(0.2, 0.9)))
        bench_fin = fin_bench(round(tau, 4))
        bench_ov = benchmark_row("zzz", financial=round(tau, 4),
                                 overall=round(tau * 0.86 + 8.8462, 4), recover=0.5, capital=0.0, target=100.0)
        for axis, bench, authority in (("financial", bench_fin, FIN), ("overall", bench_ov, V12)):
            win_map = {p: bool(cand.compare(scores[p], bench, authority=authority)) for p in scores}
            top = max((p for p in win_map if win_map[p]), default=None)
            result = branch_and_bound_highest_win(
                cand, 1, span, benchmark=bench, axis=axis, exhaustive_win=win_map, exhaustive_score=finals,
            )
            assert result.highest_winning_cent == top
            assert result.false_prunes == 0 and result.bound_violations == 0
            pruned += result.pruned_cents
    assert checked > 50
    assert pruned > 0   # the bound is not vacuous


# ---------------------------------------------------------------------------
# Auditor plumbing
# ---------------------------------------------------------------------------

def test_scope_quantities_covers_the_exact_search_range_plus_one_beyond_threshold():
    from backend.scripts.research_best_open_price_v2_monotonicity import scope_quantities

    # Non-leader on both axes: current q=4, thresholds q=6 (Overall) and q=5 (Financial).
    scope = scope_quantities(130000, {"overall": (4, 6), "financial": (4, 5)})
    assert scope == [4, 5, 6, 7]
    # Leader axis starts at q=1.
    assert scope_quantities(130000, {"overall": (1, 3)}) == [1, 2, 3, 4]
    # Explicit extras are deduped and out-of-range quantities dropped.
    assert scope_quantities(1000, {"overall": (2, 3)}, extra=[3, 4, 5000]) == [2, 3, 4]


def test_merge_analysis_counts_sweeps_that_are_not_down_closed():
    from backend.scripts.research_best_open_price_v2_monotonicity import merge_analysis

    cand = candidate(REBOUND)
    bench = fin_bench(82.9319)
    rows = sweep_interval(cand, 250, 400, financial_benchmark=bench, overall_benchmark=bench)
    monotone_rows = sweep_interval(cand, 401, 519, financial_benchmark=fin_bench(76.0),
                                   overall_benchmark=fin_bench(76.0))
    merged = merge_analysis([analyze_rows(rows, "financial"), analyze_rows(monotone_rows, "financial")])
    assert merged["sweeps"] == 2 and merged["sweepsNotDownClosed"] == 1
    assert merged["lossToWinTransitions"] >= 1
