# Best-Open Price V2 — Phases 1-3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the canonical Financial-only comparator into a reusable function (Phase 1), split candidate price scoring from winner-determination in the Best-Open exact-search engine so a candidate can be judged by either the OVERALL_V12 or the new FINANCIAL_V4 comparison authority (Phase 2), and introduce a shared score cache so scoring a given (quantity, price_cents) candidate once serves both authorities instead of twice (Phase 3). This plan does NOT build the dual-threshold search loop itself, the V2 row contract, the migration, or the RPC — those are Phases 4-9, planned separately after this lands.

**Architecture:** `rank_budget_cohort()` in `backend/calculations/evr/budget_normalized_product_ranking.py` already computes an internal "Financial RIP V4 only" ordering (`financialOnlyRank`) inline, over the same `rankable` cohort it uses for the primary V10/V12 order. Phase 1 extracts that ordering into a standalone `rank_by_financial_only()` function with identical behavior, verified by pinning `rank_budget_cohort`'s existing `financialOnlyRank` output before and after. Phase 2 gives `PreparedCanonicalCandidate` (in `backend/calculations/evr/best_open_price.py`) a `score_candidate()` method that does pure Financial RIP V3/V4/V12 scoring with no comparison, and a `compare()` method that dispatches to either `rank_budget_cohort(..., sort_authority=SORT_AUTHORITY_V12)` (existing behavior) or the new `rank_by_financial_only()`, selected by a `comparison_authority` keyword defaulting to the existing V12 behavior so `evaluate()`'s public two-positional-argument signature and V1's existing callers/tests are unaffected. Phase 3 adds `SharedScoreCache`, a small `(quantity, price_cents)`-keyed cache wrapping `score_candidate()`, so a future dual-search engine (Phase 4) can score a candidate price once and cheaply compare it under both authorities via `SharedScoreCache.evaluate()`.

**Tech Stack:** Python 3, pytest, dataclasses.

**Spec:** No separate spec file — this plan implements Phases 1-3 of the "BEST-OPEN PRICE V2 — DUAL FINANCIAL + RIP THRESHOLDS" task instructions the user supplied directly in conversation (reproduced in full in the session that authorized this plan; Phase 0 of the same instructions is already merged to `develop` as commit `7411867a`). Phases 4-10 of those instructions are explicitly out of scope for this plan.

## Global Constraints

- Do NOT modify unrelated Market Explorer, onboarding, alerts, scraper, Collector Appeal, or other concurrent work.
- Do NOT touch the conflicted normal checkout `D:\EVRCalculator` — all work happens in this worktree (`D:\EVRCalculator\.claude\worktrees\best-open-price-v2`, detached at `origin/develop`).
- Do NOT alter Financial RIP V4 or Overall RIP V12 scoring methodology — Phase 1-3 work is purely structural (extraction, parameterization, caching), never a change to a score formula.
- Do NOT weaken exact-search/maximality guarantees — `ExactBestOpenPriceSearch`'s existing `evaluate_price`/`_search_leader`/`_search_non_leader`/`search()` logic in `best_open_price.py` is NOT modified by this plan; only `PreparedCanonicalCandidate.evaluate()` gains an optional authority parameter, and a new, additive `SharedScoreCache` class is introduced alongside it.
- `PreparedCanonicalCandidate.evaluate(price_cents, benchmark)` — called positionally by `ExactBestOpenPriceSearch.evaluate_price()` at `best_open_price.py:214` and by the test at `test_prepared_financial_rip_and_best_open_price.py:190-193` — must keep working unchanged after Phase 2; the new `comparison_authority` parameter must be keyword-only with a default that reproduces today's behavior exactly.
- `rank_budget_cohort()`'s existing return value and `financialOnlyRank` output must not change for any existing caller (`build_budget_normalized_product_rankings.py`, and every test enumerated in the Phase 1 task) — Phase 1 is a pure extraction, not a behavior change.
- **Git workflow authority (overrides this plan's or any skill's default branch/PR behavior):** build directly on `develop`. Do NOT create a feature branch. Do NOT open a PR. Work only in `D:\EVRCalculator\.claude\worktrees\best-open-price-v2`, kept detached at the current `origin/develop` head. For each task's reviewed checkpoint: (1) `git fetch origin develop`, (2) confirm `origin/develop` has not advanced unexpectedly since this task started, (3) the task's tests/review must already be green, (4) commit the bounded change, (5) push directly with `git push origin HEAD:develop`. Never force-push. If `origin/develop` has advanced, STOP and reconcile (rebase this task's commit onto the new head, re-run its tests) before pushing — never overwrite concurrent work. The remote branch `feature/best-open-v2-dual-threshold-core-20260916` is unused and must not be pushed to or read from.

---

### Task 1: Extract the canonical Financial-only comparator

**Files:**
- Modify: `backend/calculations/evr/budget_normalized_product_ranking.py:427-496` (inside `rank_budget_cohort`)
- Test: `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py`

**Interfaces:**
- Produces: `financial_only_comparator_key(entry: Mapping[str, Any]) -> tuple` and `rank_by_financial_only(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]`, both new module-level functions in `budget_normalized_product_ranking.py`. `rank_by_financial_only` takes an already-filtered cohort (callers control membership; it does not filter by `overallRipV12Rankable`/`overallRipV10Score`), sorts it by `financial_only_comparator_key`, and returns one shallow-copied dict per input entry with an added 1-based `"financialOnlyRank"` key, in sorted order. This is a general-purpose export: Task 2 will pass it a 2-element `[candidate, benchmark]` list for pairwise Financial-only winner determination, the same way `rank_budget_cohort` is already used pairwise inside `PreparedCanonicalCandidate.evaluate()`.
- Consumes (unchanged): nothing new — `rank_budget_cohort`'s existing `rankable` list (already filtered by `sort_authority`) becomes the input to the new `rank_by_financial_only`.

- [ ] **Step 1: Write the failing pinning test**

Add to `backend/tests/unit/calculations/test_budget_normalized_product_ranking.py`, near the existing `financial_only_rank` tests (search for `# --- financial_only_rank (internal audit lens) ---`, around line 264):

```python
def test_rank_by_financial_only_extraction_matches_rank_budget_cohort_output():
    """Task 1 pinning test: the extracted rank_by_financial_only() helper must
    reproduce rank_budget_cohort()'s existing financialOnlyRank output exactly,
    when called on the SAME rankable cohort rank_budget_cohort itself sorts on.
    This is a refactor, not a behavior change -- both computations must agree
    for every entry, in both directions.
    """
    strategies = [
        {"sealedProductId": "efficient", "overallRipV12Rankable": True, "overallRipV12Score": 40.0,
         "financialRipV4Score": 95.0, "actualCommittedCapital": 100.0, "targetBudget": 100.0},
        {"sealedProductId": "appealing", "overallRipV12Rankable": True, "overallRipV12Score": 90.0,
         "financialRipV4Score": 60.0, "actualCommittedCapital": 100.0, "targetBudget": 100.0},
        {"sealedProductId": "unrankable", "overallRipV12Rankable": False, "overallRipV12Score": None,
         "financialRipV4Score": 99.0, "actualCommittedCapital": 100.0, "targetBudget": 100.0},
    ]

    ranked = rank_budget_cohort(strategies, sort_authority=SORT_AUTHORITY_V12)
    by_id = {row["sealedProductId"]: row for row in ranked}

    # rank_budget_cohort's own financialOnlyRank output is the ground truth
    # this task must not change.
    assert by_id["efficient"]["financialOnlyRank"] == 1
    assert by_id["appealing"]["financialOnlyRank"] == 2
    assert "unrankable" not in by_id  # excluded from the V12-rankable cohort entirely

    # The SAME rankable cohort rank_budget_cohort sorts on (V12-rankable
    # entries only) fed directly into the extracted helper must agree exactly.
    v12_rankable = [s for s in strategies if s.get("overallRipV12Rankable") is True and s.get("overallRipV12Score") is not None]
    extracted = rank_by_financial_only(v12_rankable)
    extracted_by_id = {row["sealedProductId"]: row["financialOnlyRank"] for row in extracted}
    assert extracted_by_id == {"efficient": 1, "appealing": 2}


def test_rank_by_financial_only_orders_desc_by_score_then_id_tiebreak():
    strategies = [
        {"sealedProductId": "b", "financialRipV4Score": 50.0},
        {"sealedProductId": "a", "financialRipV4Score": 50.0},
        {"sealedProductId": "c", "financialRipV4Score": 70.0},
    ]
    ranked = rank_by_financial_only(strategies)
    assert [row["sealedProductId"] for row in ranked] == ["c", "a", "b"]
    assert [row["financialOnlyRank"] for row in ranked] == [1, 2, 3]


def test_rank_by_financial_only_treats_missing_score_as_lowest():
    strategies = [
        {"sealedProductId": "scored", "financialRipV4Score": 1.0},
        {"sealedProductId": "unscored", "financialRipV4Score": None},
    ]
    ranked = rank_by_financial_only(strategies)
    assert [row["sealedProductId"] for row in ranked] == ["scored", "unscored"]
```

These three tests import `rank_by_financial_only` (and use the already-imported `rank_budget_cohort`, `SORT_AUTHORITY_V12` — confirm these imports already exist at the top of the test file; add `rank_by_financial_only` to the existing `from backend.calculations.evr.budget_normalized_product_ranking import (...)` block if there is one, otherwise add a new import line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py -k "rank_by_financial_only" -v`

Expected: FAIL with `ImportError` or `AttributeError` — `rank_by_financial_only` does not exist yet.

- [ ] **Step 3: Extract the helper**

In `backend/calculations/evr/budget_normalized_product_ranking.py`, add these two new module-level functions immediately before `def rank_budget_cohort(`  (i.e., right after `_tier_sort_key_v12`, before line 427):

```python
def financial_only_comparator_key(entry: Mapping[str, Any]) -> tuple:
    """Financial RIP V4 (desc) -> sealed_product_id (deterministic tie-break).

    The comparator behind rank_by_financial_only(): the same sort key
    rank_budget_cohort() has always used for its internal financialOnlyRank
    audit lens, extracted so Best-Open Price V2's FINANCIAL_V4 comparison
    authority can reuse it directly instead of reimplementing the sort.
    """
    financial = entry.get("financialRipV4Score")
    return (
        -(financial if financial is not None else float("-inf")),
        str(entry.get("sealedProductId") or ""),
    )


def rank_by_financial_only(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Canonical Financial-only comparator.

    Orders the GIVEN strategies by financial_only_comparator_key and assigns
    1-based ranks. Callers control cohort membership -- this function applies
    no rankability filter of its own, matching how rank_budget_cohort() has
    always called this ordering only on its own pre-filtered `rankable` list.
    Used both by rank_budget_cohort() (for its internal financialOnlyRank
    audit lens) and by Best-Open Price V2's FINANCIAL_V4 comparison authority
    for pairwise candidate-vs-benchmark winner determination.
    """
    ordered = sorted(strategies, key=financial_only_comparator_key)
    return [
        {**entry, "financialOnlyRank": index}
        for index, entry in enumerate(ordered, start=1)
    ]
```

Then replace the inline block inside `rank_budget_cohort` (currently lines 473-483):

```python
    financial_only = sorted(
        rankable,
        key=lambda e: (
            -(e["financialRipV4Score"] if e.get("financialRipV4Score") is not None else float("-inf")),
            str(e.get("sealedProductId") or ""),
        ),
    )
    financial_only_rank = {
        str(entry.get("sealedProductId")): index
        for index, entry in enumerate(financial_only, start=1)
    }
```

with:

```python
    financial_only_rank = {
        str(entry.get("sealedProductId")): entry["financialOnlyRank"]
        for entry in rank_by_financial_only(rankable)
    }
```

Leave the surrounding `out = []` / `for index, entry in enumerate(ordered, start=1):` block (lines 485-496) completely unchanged — it already reads `financial_only_rank[str(entry.get("sealedProductId"))]` and will work identically against the new dict.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py -k "rank_by_financial_only" -v`

Expected: PASS, all 3 new tests.

- [ ] **Step 5: Run the full existing test file to confirm zero behavior change**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py -v`

Expected: PASS, including the four pre-existing `financial_only_rank` tests (`test_financial_only_rank_orders_by_v4_independently_of_overall_rank`, `test_financial_only_rank_covers_the_same_cohort_contiguously`, `test_financial_only_rank_excludes_unrankable_strategies_like_the_primary_rank`, `test_financial_only_rank_is_deterministic`) — these prove the refactor changed nothing observable about `rank_budget_cohort`'s output.

- [ ] **Step 6: Run downstream consumers**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_build_budget_normalized_product_rankings_v12_publication.py backend/tests/unit/scripts/test_build_budget_product_rankings_payload.py -v` (these read `financial_only_rank`/`financialOnlyRank` off published rows, per the research in this plan's authoring session).

Expected: PASS, unchanged.

- [ ] **Step 7: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm still 7411867a; if it has advanced, STOP and reconcile per Global Constraints before continuing
git add backend/calculations/evr/budget_normalized_product_ranking.py backend/tests/unit/calculations/test_budget_normalized_product_ranking.py
git commit -m "refactor: extract rank_by_financial_only() canonical comparator"
git push origin HEAD:develop
```

---

### Task 2: Separate price scoring from comparison, add the FINANCIAL_V4 authority

**Files:**
- Modify: `backend/calculations/evr/best_open_price.py:32-78` (`PreparedCanonicalCandidate`)
- Test: `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`

**Interfaces:**
- Consumes: `rank_by_financial_only` from Task 1 (`backend.calculations.evr.budget_normalized_product_ranking`).
- Produces: two new module-level string constants in `best_open_price.py`, `COMPARISON_AUTHORITY_OVERALL_V12 = "overall_v12"` and `COMPARISON_AUTHORITY_FINANCIAL_V4 = "financial_v4"`. `PreparedCanonicalCandidate` gains `score_candidate(self, price_cents: int) -> Dict[str, Any]` (pure scoring, no comparison — returns everything `evaluate()` used to put in its `candidate` dict, plus `priceCents`, `quantity`, `financialRipV3Score`, `scoringSeconds`) and `compare(self, score_record: Mapping[str, Any], benchmark: Mapping[str, Any], *, authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> bool`. `evaluate()`'s signature becomes `evaluate(self, price_cents: int, benchmark: Mapping[str, Any], *, comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> Dict[str, Any]` — the two positional parameters and the default behavior are unchanged; it now returns the same dict shape it always did, built from `score_candidate()` + `compare()`, plus `"comparisonAuthority": comparison_authority` (new key, safe to add — no existing consumer reads a fixed key set that would reject an extra key).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`, after the existing `test_candidate_committed_capital_matches_canonical_allocation_float_order` (end of file):

```python
from backend.calculations.evr.best_open_price import (
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
)


def _prepared_candidate(product_id, quantity, *, collector_appeal=60.0, chase_accessibility=0.002,
                         budget=1300.0, seed=20260916):
    values = np.random.default_rng(seed).lognormal(2.0, 1.2, 20_000)
    prepared = PreparedFinancialRipDistribution.prepare(values)
    return PreparedCanonicalCandidate(product_id, quantity, prepared, collector_appeal, chase_accessibility, budget)


def test_evaluate_default_authority_is_unchanged_overall_v12():
    """Task 2 backward-compat pin: evaluate() called exactly as V1 callers
    call it (two positional args, no authority) must return the identical
    'wins' determination it always did -- comparator authority defaults to
    OVERALL_V12.
    """
    candidate = _prepared_candidate("candidate", 9)
    benchmark = {"sealedProductId": "benchmark", "overallRipV12Score": -1e9, "overallRipV12Rankable": True,
                 "financialRipV4Score": -1e9}
    result = candidate.evaluate(14068, benchmark)
    assert result["comparisonAuthority"] == COMPARISON_AUTHORITY_OVERALL_V12
    assert "wins" in result and "financialRipV4Score" in result and "overallRipV12Score" in result


def test_score_candidate_has_no_comparison_fields():
    candidate = _prepared_candidate("candidate", 9)
    record = candidate.score_candidate(14068)
    assert "wins" not in record
    assert record["sealedProductId"] == "candidate"
    assert record["priceCents"] == 14068
    assert record["quantity"] == 9
    assert isinstance(record["financialRipV4Score"], float)


def test_compare_under_financial_v4_authority_uses_financial_only_comparator(monkeypatch):
    candidate = _prepared_candidate("candidate", 9)
    score_record = {"sealedProductId": "candidate", "financialRipV4Score": 50.0}
    losing_benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": 10.0}
    winning_benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": 90.0}
    assert candidate.compare(score_record, losing_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4) is True
    assert candidate.compare(score_record, winning_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4) is False


def test_compare_under_overall_v12_authority_is_unchanged(monkeypatch):
    candidate = _prepared_candidate("candidate", 9)
    score_record = {"sealedProductId": "candidate", "overallRipV12Rankable": True, "overallRipV12Score": 90.0,
                     "financialRipV4Score": 50.0}
    losing_benchmark = {"sealedProductId": "benchmark", "overallRipV12Rankable": True, "overallRipV12Score": 10.0,
                         "financialRipV4Score": 10.0}
    assert candidate.compare(score_record, losing_benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12) is True


def test_evaluate_under_financial_v4_authority_can_disagree_with_overall_v12():
    """A candidate can win under FINANCIAL_V4 while losing under OVERALL_V12
    against the SAME benchmark -- the two authorities are genuinely
    independent, per Phase 4's requirement that a product may be #1 under one
    authority but not the other.
    """
    candidate = _prepared_candidate("candidate", 9)
    score_record = candidate.score_candidate(14068)
    high_v4_low_v12_benchmark = {
        "sealedProductId": "benchmark",
        "financialRipV4Score": score_record["financialRipV4Score"] - 1.0,  # candidate wins FINANCIAL_V4
        "overallRipV12Rankable": True,
        "overallRipV12Score": (score_record.get("overallRipV12Score") or 0.0) + 1000.0,  # candidate loses OVERALL_V12
    }
    wins_financial = candidate.compare(score_record, high_v4_low_v12_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)
    wins_overall = candidate.compare(score_record, high_v4_low_v12_benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert wins_financial is True
    assert wins_overall is False


def test_compare_rejects_unknown_authority():
    candidate = _prepared_candidate("candidate", 9)
    with pytest.raises(ValueError, match="comparison authority"):
        candidate.compare({"sealedProductId": "candidate"}, {"sealedProductId": "benchmark"}, authority="not_a_real_authority")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "authority or score_candidate or compare" -v`

Expected: FAIL — `COMPARISON_AUTHORITY_FINANCIAL_V4`/`COMPARISON_AUTHORITY_OVERALL_V12` don't exist, `score_candidate`/`compare` don't exist.

- [ ] **Step 3: Refactor `PreparedCanonicalCandidate`**

In `backend/calculations/evr/best_open_price.py`, add the import and constants near the top (after the existing imports, before `BEST_OPEN_PRICE_METHOD_VERSION`):

```python
from backend.calculations.evr.budget_normalized_product_ranking import (
    SORT_AUTHORITY_V12,
    rank_budget_cohort,
    rank_by_financial_only,
)
```

(this replaces the existing `from backend.calculations.evr.budget_normalized_product_ranking import (SORT_AUTHORITY_V12, rank_budget_cohort)` block at lines 11-14 — add `rank_by_financial_only` to it)

```python
BEST_OPEN_PRICE_METHOD_VERSION = "budget_product_best_open_price_full_market_v1"

COMPARISON_AUTHORITY_OVERALL_V12 = "overall_v12"
COMPARISON_AUTHORITY_FINANCIAL_V4 = "financial_v4"
```

Then replace the entire `PreparedCanonicalCandidate.evaluate()` method (current lines 42-78) with:

```python
    def score_candidate(self, price_cents: int) -> Dict[str, Any]:
        """Pure candidate-price scoring. No comparison, no winner determination."""
        score_started = time.perf_counter()
        # Mirror whole_unit_allocation() exactly. The canonical Budget Ranking
        # first converts the cent price to a float dollar price and THEN
        # multiplies by quantity. Reordering these IEEE-754 operations
        # (quantity * cents / 100) can change the stored float by ~1e-13 and,
        # at a Financial RIP rounding boundary, change the published score.
        unit_price = price_cents / 100.0
        capital = self.quantity * unit_price
        kwargs = {} if not self.min_simulation_count else {"min_simulation_count": self.min_simulation_count}
        v3 = self.distribution.score(capital, **kwargs)
        v4 = project_financial_rip_v4_from_v3_payload(v3)
        v12 = compute_overall_rip_v12(
            v4.get("score"), self.chase_accessibility_raw, self.collector_appeal_score
        )
        raw = {key: record.get("raw") for key, record in
               ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        scoring_seconds = time.perf_counter() - score_started
        return {
            "sealedProductId": self.product_id,
            "priceCents": price_cents,
            "quantity": self.quantity,
            "targetBudget": self.target_budget,
            "actualCommittedCapital": capital,
            "financialRipV3Score": v3.get("score"),
            "financialRipV4Score": v4.get("score"),
            "overallRipV12Score": v12.get("score"),
            "overallRipV12Rankable": bool(v12.get("rankable")),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
            "scoringSeconds": scoring_seconds,
        }

    def compare(self, score_record: Mapping[str, Any], benchmark: Mapping[str, Any], *,
                authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> bool:
        """Winner determination only. Never rescoring -- score_record is already computed."""
        comparator_started = time.perf_counter()
        if authority == COMPARISON_AUTHORITY_OVERALL_V12:
            ranked = rank_budget_cohort([score_record, dict(benchmark)], sort_authority=SORT_AUTHORITY_V12)
        elif authority == COMPARISON_AUTHORITY_FINANCIAL_V4:
            ranked = rank_by_financial_only([score_record, dict(benchmark)])
        else:
            raise ValueError(f"unknown comparison authority {authority!r}")
        self._last_comparator_seconds = time.perf_counter() - comparator_started
        return bool(ranked and ranked[0]["sealedProductId"] == self.product_id)

    def evaluate(self, price_cents: int, benchmark: Mapping[str, Any], *,
                 comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12) -> Dict[str, Any]:
        score_record = self.score_candidate(price_cents)
        wins = self.compare(score_record, benchmark, authority=comparison_authority)
        comparator_seconds = getattr(self, "_last_comparator_seconds", 0.0)
        return {
            "wins": wins,
            "priceCents": score_record["priceCents"],
            "quantity": score_record["quantity"],
            "financialRipV3Score": score_record["financialRipV3Score"],
            "financialRipV4Score": score_record["financialRipV4Score"],
            "overallRipV12Score": score_record["overallRipV12Score"],
            "chanceToRecoverCapital": score_record["chanceToRecoverCapital"],
            "actualCommittedCapital": score_record["actualCommittedCapital"],
            "scoringSeconds": score_record["scoringSeconds"],
            "comparatorSeconds": comparator_seconds,
            "comparisonAuthority": comparison_authority,
        }
```

`_last_comparator_seconds` is a plain instance attribute, not a dataclass field — `PreparedCanonicalCandidate` is a `@dataclass` without `slots=True` (confirmed: no `slots` argument on the `@dataclass` decorator at line 32), so setting an attribute not declared as a dataclass field in `__init__` works exactly like on any ordinary Python object; do not add it to the dataclass field list.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "authority or score_candidate or compare" -v`

Expected: PASS, all 6 new tests.

- [ ] **Step 5: Run the full existing test file to confirm zero regression**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -v`

Expected: PASS, including every pre-existing test (`test_nonleader_exact_search_never_above_market_and_transitions_quantity`, `test_leader_allows_headroom_excludes_self_and_is_maximal`, `test_search_matches_bruteforce_oracle_and_is_repeatable`, `test_authority_version_cache_isolation_and_cleanup`, `test_candidate_committed_capital_matches_canonical_allocation_float_order`, etc.) — these exercise `ExactBestOpenPriceSearch`, which calls `PreparedCanonicalCandidate.evaluate(price_cents, self.benchmark)` positionally at `best_open_price.py:214` and must be completely unaffected.

- [ ] **Step 6: Run the Best-Open publication test suite (consumer of this module)**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py backend/tests/unit/scripts/test_build_budget_product_best_open_price_snapshot.py -v`

Expected: PASS, unchanged (neither file constructs `PreparedCanonicalCandidate` directly with positional-only assumptions beyond what Step 5 already covers, but this confirms the publication path still imports and runs cleanly).

- [ ] **Step 7: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 1 just pushed; if it has advanced further, STOP and reconcile before continuing
git add backend/calculations/evr/best_open_price.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py
git commit -m "refactor: separate Best-Open candidate scoring from comparison, add FINANCIAL_V4 authority"
git push origin HEAD:develop
```

---

### Task 3: Shared score cache across comparison authorities

**Files:**
- Modify: `backend/calculations/evr/best_open_price.py` (add `SharedScoreCache` after `PreparedCanonicalCandidate`, before `ExactBestOpenPriceSearch`)
- Test: `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`

**Interfaces:**
- Consumes: `PreparedCanonicalCandidate.score_candidate` and `.compare` from Task 2.
- Produces: `SharedScoreCache`, a new dataclass in `best_open_price.py` with `get_or_score(self, candidate: PreparedCanonicalCandidate, price_cents: int) -> Dict[str, Any]` (scores once per `(quantity, price_cents)` key, LRU-evicted like `ExactBestOpenPriceSearch._quantities`), `evaluate(self, candidate: PreparedCanonicalCandidate, price_cents: int, benchmark: Mapping[str, Any], *, authority: str) -> Dict[str, Any]` (calls `get_or_score` then `candidate.compare(...)`, returns `{**score_record, "wins": wins}`), and `diagnostics(self) -> Dict[str, Any]` returning `{"uniqueCandidatePricesScored": int, "sharedScoreCacheHits": int, "financialComparatorEvaluations": int, "ripComparatorEvaluations": int}` — the four diagnostic fields the plan's Phase 3 spec requires, ready for a future Phase 4 dual-search engine to report. This is a standalone, additively-tested unit in this plan; no existing code is wired to use it yet (that wiring is Phase 4, out of scope here).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`, after Task 2's tests (end of file):

```python
from backend.calculations.evr.best_open_price import SharedScoreCache


def test_shared_score_cache_scores_once_across_both_authorities():
    """The core Phase 3 promise: a (quantity, price_cents) candidate scored
    once must serve BOTH comparison authorities without rescoring -- the
    Financial RIP V3 Monte Carlo simulation is the expensive part, and the
    comparator dispatch itself is cheap.
    """
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}

    first = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    second = cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)

    assert first["wins"] is True and second["wins"] is True
    # Same underlying score for the same (quantity, price_cents) -- proves no rescoring happened.
    assert first["financialRipV4Score"] == second["financialRipV4Score"]
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 1
    assert diagnostics["sharedScoreCacheHits"] == 1  # the second evaluate() call hit the cache
    assert diagnostics["ripComparatorEvaluations"] == 1
    assert diagnostics["financialComparatorEvaluations"] == 1


def test_shared_score_cache_distinguishes_price_cents_within_same_quantity():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    cache.evaluate(candidate, 14069, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 2
    assert diagnostics["sharedScoreCacheHits"] == 0


def test_shared_score_cache_get_or_score_matches_direct_score_candidate():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache()
    cached = cache.get_or_score(candidate, 14068)
    direct = candidate.score_candidate(14068)
    assert cached["financialRipV4Score"] == direct["financialRipV4Score"]
    assert cached["actualCommittedCapital"] == direct["actualCommittedCapital"]


def test_shared_score_cache_evicts_beyond_max_entries():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache(max_entries=2)
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    for price in (14068, 14069, 14070):
        cache.evaluate(candidate, price, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert len(cache._scores) == 2
    # Oldest entry (14068) evicted; re-requesting it must score again, not hit.
    diagnostics_before = cache.diagnostics()["uniqueCandidatePricesScored"]
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert cache.diagnostics()["uniqueCandidatePricesScored"] == diagnostics_before + 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "shared_score_cache" -v`

Expected: FAIL — `SharedScoreCache` does not exist yet.

- [ ] **Step 3: Implement `SharedScoreCache`**

In `backend/calculations/evr/best_open_price.py`, insert this new class between `PreparedCanonicalCandidate` and `ExactBestOpenPriceSearch` (i.e., right after the `evaluate()` method's closing line from Task 2, before the `@dataclass` line that starts `ExactBestOpenPriceSearch`):

```python
@dataclass
class SharedScoreCache:
    """Scores a (quantity, price_cents) candidate once, serves every
    comparison authority against it from the same score record.

    The Financial RIP V3 Monte Carlo simulation inside
    PreparedCanonicalCandidate.score_candidate() is the expensive step; the
    comparator dispatch inside .compare() is cheap. A dual-threshold engine
    (RIP + FINANCIAL_V4 searches over the same product) shares this cache so
    neither search rescoring a price the other already scored.
    """
    max_entries: int = 4096
    _scores: "OrderedDict[tuple[int, int], Dict[str, Any]]" = field(default_factory=OrderedDict, init=False)
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)
    financial_comparator_evaluations: int = field(default=0, init=False)
    rip_comparator_evaluations: int = field(default=0, init=False)

    def get_or_score(self, candidate: "PreparedCanonicalCandidate", price_cents: int) -> Dict[str, Any]:
        key = (candidate.quantity, price_cents)
        if key in self._scores:
            self.hits += 1
            self._scores.move_to_end(key)
            return self._scores[key]
        self.misses += 1
        record = candidate.score_candidate(price_cents)
        self._scores[key] = record
        while len(self._scores) > self.max_entries:
            self._scores.popitem(last=False)
        return record

    def evaluate(self, candidate: "PreparedCanonicalCandidate", price_cents: int,
                 benchmark: Mapping[str, Any], *, authority: str) -> Dict[str, Any]:
        score_record = self.get_or_score(candidate, price_cents)
        wins = candidate.compare(score_record, benchmark, authority=authority)
        if authority == COMPARISON_AUTHORITY_FINANCIAL_V4:
            self.financial_comparator_evaluations += 1
        elif authority == COMPARISON_AUTHORITY_OVERALL_V12:
            self.rip_comparator_evaluations += 1
        else:
            raise ValueError(f"unknown comparison authority {authority!r}")
        return {**score_record, "wins": wins}

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "uniqueCandidatePricesScored": self.misses,
            "sharedScoreCacheHits": self.hits,
            "financialComparatorEvaluations": self.financial_comparator_evaluations,
            "ripComparatorEvaluations": self.rip_comparator_evaluations,
        }
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "shared_score_cache" -v`

Expected: PASS, all 4 new tests.

- [ ] **Step 5: Run the full file and the broader Best-Open suite**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py -v`

Expected: all PASS, no regressions from Tasks 1-2.

- [ ] **Step 6: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 2 just pushed; if it has advanced further, STOP and reconcile before continuing
git add backend/calculations/evr/best_open_price.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py
git commit -m "feat: add SharedScoreCache for dual comparison-authority candidate scoring"
git push origin HEAD:develop
```

---

## Self-Review Notes

- Spec coverage: Phase 1 (extract canonical Financial comparator into one reusable helper, wire into `rank_budget_cohort`, add pre/post identity tests) is Task 1. Phase 2 (separate price scoring from comparison; two comparison authorities; authority affects only winner determination, never scoring) is Task 2, including the explicit test that Financial and RIP authorities can disagree on the same benchmark. Phase 3 (share expensive candidate work via a cache keyed by `(quantity, price_cents)`; report `uniqueCandidatePricesScored`/`financialComparatorEvaluations`/`ripComparatorEvaluations`/`sharedScoreCacheHits` diagnostics) is Task 3. Phases 4-10 (the actual dual global search loop, V2 row contract, migration, RPC, service/projection, 24-test matrix, read-only 138-product validation) are explicitly out of scope for this plan and will be planned separately, consuming Tasks 1-3's `rank_by_financial_only`, `score_candidate`/`compare`, and `SharedScoreCache`.
- No placeholders: every step has literal code.
- Type consistency: `rank_by_financial_only(strategies) -> List[Dict[str, Any]]` (Task 1) is consumed identically in Task 2's `compare()`. `PreparedCanonicalCandidate.score_candidate(price_cents) -> Dict[str, Any]` and `.compare(score_record, benchmark, *, authority) -> bool` (Task 2) are consumed identically in Task 3's `SharedScoreCache.get_or_score`/`.evaluate`. `COMPARISON_AUTHORITY_OVERALL_V12`/`COMPARISON_AUTHORITY_FINANCIAL_V4` string constants are used identically across Tasks 2 and 3.
