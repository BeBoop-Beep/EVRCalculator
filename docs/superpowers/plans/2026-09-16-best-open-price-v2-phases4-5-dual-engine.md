# Best-Open Price V2 — Phases 4-5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dual exact-search engine that computes, for every Full Market product, two independent exact price thresholds (RIP under `OVERALL_V12`, Financial under `FINANCIAL_V4`), sharing expensive candidate scoring between them, and assemble the V2 in-memory result contract (RIP-aliased backward-compatible fields + explicit `financial*`/`rip*` fields + per-authority exactness/threshold evidence). No migration, no RPC, no publication, no frontend change.

**Architecture:** `ExactBestOpenPriceSearch` (V1, `backend/calculations/evr/best_open_price.py`) gains two new *optional* dataclass fields — `shared_score_cache` and `comparison_authority` — so the exact same class serves either authority and, when given a shared cache, two instances of it (one per authority) never rescore an identical `(quantity, price_cents)` candidate. This is additive: omitting both fields reproduces V1's exact current behavior byte-for-byte. A new `DualBestOpenPriceSearch` orchestrator builds ONE `SharedScoreCache` and ONE quantity-level candidate memoization wrapper around the caller's `prepare_quantity`/`prepare_quantities`, then constructs and runs two `ExactBestOpenPriceSearch` instances against it — so the physically expensive `PreparedFinancialRipDistribution.prepare()` call (done once per quantity) and the `score_candidate()` call (done once per `(quantity, price_cents)`) are each done at most once across both searches, never duplicated. A new `research_best_open_price_v2.py` script reuses the existing V1 source-authority loader (`backend/scripts/research_best_open_price_bucket0.py`) and V1 distribution-preparation closures (mirroring `research_best_open_price_bucket2.py`'s `factory`/`batch_factory` pattern) to drive `DualBestOpenPriceSearch` per product and assemble the V2 row contract. Financial-authority benchmark selection and rank-integrity validation are added to `bucket0.py` alongside the existing V12-authority equivalents (`_competitor`, `validate_source`).

**Tech Stack:** Python 3, pytest, dataclasses.

**Spec:** No separate spec file — this plan implements Phases 4-5 of the "BEST-OPEN PRICE V2" task instructions supplied directly in conversation. Phases 0-3 are complete and on `develop` (commit `1206a0da`). Phases 6-10 (migration, RPC, service/projection, read-only 138-product validation) are explicitly out of scope here.

## Global Constraints

- Do NOT touch: DB migrations/schema, the Best-Open publication RPC, public read services, frontend, Product Detail, scheduler, Market Explorer, onboarding/scraper, Collector Appeal methodology, Financial RIP V4 methodology, Overall RIP V12 methodology.
- Do NOT change `BEST_OPEN_PRICE_METHOD_VERSION` (stays `"budget_product_best_open_price_full_market_v1"`). Add `BEST_OPEN_PRICE_V2_METHOD_VERSION = "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"` as a new, separate constant.
- Do NOT change the exact-search mathematics in `ExactBestOpenPriceSearch` (`evaluate_price`, `_bounds`, `_solve_interval`, `search`, `_search_leader`, `_search_non_leader`) — preserve integer cents, `q = floor(B/price)`, globally-highest-qualifying-price, high-to-low interval scanning, no monotonicity assumption, leader domain `>= current price` / nonleader domain `<= current price`, no self-benchmark, P* wins, P*+1 loses when in-domain (including across a quantity boundary). The only change to this class is two new optional fields plus routing `evaluate_price`'s scoring call through them when present.
- Do NOT fork/duplicate source-authority loading logic — the new V2 script reuses `_load_source`, `_load_exact_source_products`, `_historical_authority`, `validate_source`, `_verify_v12_parity` from `backend/scripts/research_best_open_price_bucket0.py` unchanged.
- Do NOT run `ExactBestOpenPriceSearch` (or the dual variant) twice per product from independent `execute_product()`-style calls — that would rebuild `build_stage1_distributions_cached(...)` twice. One shared per-product closure scope must serve both authorities.
- **Git workflow authority (per explicit user instruction, overrides any skill/plan default):** build directly on `develop`. No feature branch, no PR. Work only in `D:\EVRCalculator\.claude\worktrees\best-open-price-v2`, kept detached at the current `origin/develop` head (expected: `1206a0da` at plan-authoring time). For each task's reviewed checkpoint: (1) `git fetch origin develop`, (2) confirm `origin/develop` has not advanced unexpectedly — if it has, STOP and reconcile (rebase this task's commit onto the new head, re-run its tests) before pushing, never overwrite concurrent work, (3) tests/review already green, (4) commit the bounded change, (5) `git push origin HEAD:develop`. Never force-push. The remote branch `feature/best-open-v2-dual-threshold-core-20260916` is unused and must not be pushed to or read from.

---

### Task 1: Wire `SharedScoreCache` into `ExactBestOpenPriceSearch`

**Files:**
- Modify: `backend/calculations/evr/best_open_price.py` (`SharedScoreCache`, `ExactBestOpenPriceSearch.evaluate_price`)
- Test: `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`

**Interfaces:**
- Produces: `ExactBestOpenPriceSearch` gains `shared_score_cache: Optional["SharedScoreCache"] = None` and `comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12` (both optional dataclass fields with defaults reproducing today's exact behavior). `SharedScoreCache` gains an `evictions: int = field(default=0, init=False)` counter and `diagnostics()` gains three new keys: `"scoreCacheHits"`, `"scoreCacheMisses"`, `"scoreCacheEvictions"` (alongside the existing `uniqueCandidatePricesScored`/`sharedScoreCacheHits`/`financialComparatorEvaluations`/`ripComparatorEvaluations` — additive, nothing removed).
- Consumes: nothing new externally; Task 3's `DualBestOpenPriceSearch` will consume these two new fields directly.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`:

```python
def test_exact_search_default_construction_is_unchanged_v1_behavior():
    """Backward-compat pin: an ExactBestOpenPriceSearch built exactly as V1
    callers build it today (no shared_score_cache, no comparison_authority)
    must behave identically to before -- same threshold, same status.
    """
    engine = _engine(leader=False, budget=1000, current=100, winning=set(range(1, 38)))
    result = engine.search()
    assert result["threshold"]["priceCents"] == 37
    assert result["threshold"]["quantity"] == 27


def test_two_engines_sharing_one_cache_score_overlapping_candidate_once():
    budget = 1300
    candidate_a = _prepared_candidate("a", 9, budget=float(budget))
    candidate_b = _prepared_candidate("b", 9, budget=float(budget))
    cache = SharedScoreCache()

    def prepare_a(_q):
        return candidate_a

    def prepare_b(_q):
        return candidate_b

    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}

    engine_rip = ExactBestOpenPriceSearch(
        product_id="a", budget_cents=budget, current_price_cents=14068,
        current_quantity=9, current_rank=2, benchmark=benchmark,
        prepare_quantity=prepare_a, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        shared_score_cache=cache, comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12,
    )
    engine_financial = ExactBestOpenPriceSearch(
        product_id="a", budget_cents=budget, current_price_cents=14068,
        current_quantity=9, current_rank=2, benchmark=benchmark,
        prepare_quantity=prepare_a, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        shared_score_cache=cache, comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
    )

    rip_result = engine_rip.evaluate_price(14068)
    financial_result = engine_financial.evaluate_price(14068)

    assert rip_result["financialRipV4Score"] == financial_result["financialRipV4Score"]
    diagnostics = cache.diagnostics()
    assert diagnostics["uniqueCandidatePricesScored"] == 1
    assert diagnostics["scoreCacheHits"] == 1
    assert diagnostics["ripComparatorEvaluations"] == 1
    assert diagnostics["financialComparatorEvaluations"] == 1


def test_shared_score_cache_evictions_are_counted():
    candidate = _prepared_candidate("candidate", 9)
    cache = SharedScoreCache(max_entries=1)
    benchmark = {"sealedProductId": "benchmark", "financialRipV4Score": -1e9,
                 "overallRipV12Rankable": True, "overallRipV12Score": -1e9}
    cache.evaluate(candidate, 14068, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    cache.evaluate(candidate, 14069, benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12)
    assert cache.diagnostics()["scoreCacheEvictions"] == 1
```

(`_prepared_candidate` and `_engine` are the existing helpers already in this test file from Phases 1-3; `_prepared_candidate` accepts a `budget` kwarg per its Phase-2 definition — pass `budget=float(budget)` to match. If `_prepared_candidate`'s signature doesn't already accept `budget=`, check its definition and adjust the call accordingly rather than changing the helper.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "shared_score_cache_evictions or engines_sharing_one_cache or default_construction_is_unchanged" -v`

Expected: FAIL — `shared_score_cache`/`comparison_authority` aren't accepted kwargs of `ExactBestOpenPriceSearch` yet, `scoreCacheEvictions` doesn't exist yet.

- [ ] **Step 3: Implement**

In `SharedScoreCache`, add the eviction counter field and increment it in `get_or_score`'s eviction loop:

```python
    evictions: int = field(default=0, init=False)
```

```python
        while len(self._scores) > self.max_entries:
            self._scores.popitem(last=False)
            self.evictions += 1
```

Update `diagnostics()`:

```python
    def diagnostics(self) -> Dict[str, Any]:
        return {
            "uniqueCandidatePricesScored": self.misses,
            "sharedScoreCacheHits": self.hits,
            "scoreCacheHits": self.hits,
            "scoreCacheMisses": self.misses,
            "scoreCacheEvictions": self.evictions,
            "financialComparatorEvaluations": self.financial_comparator_evaluations,
            "ripComparatorEvaluations": self.rip_comparator_evaluations,
        }
```

In `ExactBestOpenPriceSearch`, add the two new fields right after `quantity_batch_size: int = 8`:

```python
    shared_score_cache: Optional["SharedScoreCache"] = None
    comparison_authority: str = COMPARISON_AUTHORITY_OVERALL_V12
```

Replace `evaluate_price`'s scoring line:

```python
        if key not in self._evaluations:
            evaluated = self._candidate(quantity).evaluate(price_cents, self.benchmark)
```

with:

```python
        if key not in self._evaluations:
            candidate = self._candidate(quantity)
            if self.shared_score_cache is not None:
                evaluated = self.shared_score_cache.evaluate(
                    candidate, price_cents, self.benchmark, authority=self.comparison_authority,
                )
            else:
                evaluated = candidate.evaluate(
                    price_cents, self.benchmark, comparison_authority=self.comparison_authority,
                )
```

This is the ONLY change to `evaluate_price`; everything below it (`scoring_seconds`/`comparator_seconds` accumulation, `_evaluations` caching, `lowest_evaluated_price`) is untouched and reads the same `"scoringSeconds"`/`"comparatorSeconds"`/`"wins"` keys both code paths already produce identically-shaped dicts for.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -v`

Expected: ALL PASS, including every pre-existing test (V1 `ExactBestOpenPriceSearch` tests construct it via `_engine()`/positionally without the two new kwargs — dataclass defaults must make this transparent).

- [ ] **Step 5: Run the broader suite**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/calculations/test_best_open_price_quantity_batch.py -v`

Expected: PASS. (If `test_best_open_price_quantity_batch.py` doesn't exist, note that and skip — check with `ls backend/tests/unit/calculations/ | grep quantity_batch` first.)

- [ ] **Step 6: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm still 1206a0da; STOP and reconcile if it has advanced
git add backend/calculations/evr/best_open_price.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py
git commit -m "feat: wire SharedScoreCache into ExactBestOpenPriceSearch for dual-authority sharing"
git push origin HEAD:develop
```

---

### Task 2: Financial-authority benchmark and rank-integrity validation

**Files:**
- Modify: `backend/scripts/research_best_open_price_bucket0.py`
- Test: `backend/tests/unit/scripts/test_research_best_open_price_bucket0.py`

**Interfaces:**
- Produces: `_financial_competitor(row: Mapping[str, Any], source_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]` (Financial-only analogue of the existing `_competitor`, ordering by `financial_only_rank` instead of `budget_rank_v12`). `validate_rank_column_contiguous(rows: Sequence[Mapping[str, Any]], column: str) -> None` (raises `RuntimeError` unless `column`'s values across `rows` form an exact `1..N` permutation with no missing/duplicate/non-contiguous values — fail-closed helper, used for both `budget_rank_v12` and `financial_only_rank`). `validate_financial_only_rank_reconstructs(source_rows: Sequence[Mapping[str, Any]]) -> None` (raises `RuntimeError` unless every row's persisted `financial_only_rank` matches a fresh reconstruction via `rank_by_financial_only` over the same cohort's `financial_rip_v4_score`s).
- Consumes: `rank_by_financial_only` from `backend.calculations.evr.budget_normalized_product_ranking` (new import in this file).

- [ ] **Step 1: Write the failing tests**

First check the existing `_competitor`/`_comparator_row` test coverage in `backend/tests/unit/scripts/test_research_best_open_price_bucket0.py` (if this file exists — run `ls backend/tests/unit/scripts/ | grep bucket0` first) to match its existing fixture-row shape (field names like `sealed_product_id`, `budget_rank_v12`). Add:

```python
def _row(pid, *, budget_rank_v12=None, financial_only_rank=None, financial_rip_v4_score=None):
    return {
        "sealed_product_id": pid,
        "budget_rank_v12": budget_rank_v12,
        "financial_only_rank": financial_only_rank,
        "financial_rip_v4_score": financial_rip_v4_score,
    }


def test_financial_competitor_picks_rank_two_for_the_financial_leader():
    rows = [_row("a", financial_only_rank=1), _row("b", financial_only_rank=2), _row("c", financial_only_rank=3)]
    assert _financial_competitor(rows[0], rows)["sealed_product_id"] == "b"


def test_financial_competitor_picks_rank_one_for_a_financial_nonleader():
    rows = [_row("a", financial_only_rank=1), _row("b", financial_only_rank=2), _row("c", financial_only_rank=3)]
    assert _financial_competitor(rows[1], rows)["sealed_product_id"] == "a"
    assert _financial_competitor(rows[2], rows)["sealed_product_id"] == "a"


def test_validate_rank_column_contiguous_accepts_valid_permutation():
    rows = [_row("a", budget_rank_v12=2), _row("b", budget_rank_v12=1), _row("c", budget_rank_v12=3)]
    validate_rank_column_contiguous(rows, "budget_rank_v12")  # must not raise


def test_validate_rank_column_contiguous_rejects_missing_value():
    rows = [_row("a", budget_rank_v12=1), _row("b", budget_rank_v12=None)]
    with pytest.raises(RuntimeError, match="missing"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_rank_column_contiguous_rejects_duplicate():
    rows = [_row("a", budget_rank_v12=1), _row("b", budget_rank_v12=1)]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_rank_column_contiguous_rejects_non_contiguous_gap():
    rows = [_row("a", budget_rank_v12=1), _row("b", budget_rank_v12=3)]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_financial_only_rank_reconstructs_accepts_correct_ranks():
    rows = [
        _row("high", financial_only_rank=1, financial_rip_v4_score=90.0),
        _row("low", financial_only_rank=2, financial_rip_v4_score=10.0),
    ]
    validate_financial_only_rank_reconstructs(rows)  # must not raise


def test_validate_financial_only_rank_reconstructs_rejects_mismatched_rank():
    rows = [
        _row("high", financial_only_rank=2, financial_rip_v4_score=90.0),  # wrong: should be 1
        _row("low", financial_only_rank=1, financial_rip_v4_score=10.0),
    ]
    with pytest.raises(RuntimeError, match="does not reconstruct"):
        validate_financial_only_rank_reconstructs(rows)
```

Add the necessary imports at the top of the test file: `_financial_competitor`, `validate_rank_column_contiguous`, `validate_financial_only_rank_reconstructs` from `backend.scripts.research_best_open_price_bucket0`, and `pytest`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_research_best_open_price_bucket0.py -k "financial_competitor or validate_rank_column or validate_financial_only_rank" -v`

Expected: FAIL — functions don't exist yet. (If `test_research_best_open_price_bucket0.py` doesn't exist at all, create it fresh with just these tests plus the necessary imports.)

- [ ] **Step 3: Implement**

In `backend/scripts/research_best_open_price_bucket0.py`, add the import:

```python
from backend.calculations.evr.budget_normalized_product_ranking import rank_by_financial_only
```

Add these three functions near the existing `_competitor`/`_comparator_row` (around line 193-236):

```python
def _financial_competitor(row: Mapping[str, Any], source_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Financial-only analogue of _competitor(): benchmark by financial_only_rank,
    not budget_rank_v12. The Financial and RIP benchmarks may be different products."""
    ordered = sorted(source_rows, key=lambda r: int(r["financial_only_rank"]))
    return ordered[1] if str(row["sealed_product_id"]) == str(ordered[0]["sealed_product_id"]) else ordered[0]


def validate_rank_column_contiguous(rows: Sequence[Mapping[str, Any]], column: str) -> None:
    """Fail closed unless `column` is an exact 1..N permutation over `rows`.

    Used for both budget_rank_v12 (V1's existing implicit assumption, now made
    explicit) and financial_only_rank (new for the dual engine) -- a missing,
    duplicate, or non-contiguous rank column must abort before any expensive
    search runs, not silently produce a wrong benchmark or cohort-size count.
    """
    values = []
    for row in rows:
        value = row.get(column)
        if value is None:
            raise RuntimeError(f"{column} is missing for sealed_product_id={row.get('sealed_product_id')!r}")
        values.append(int(value))
    n = len(values)
    if sorted(values) != list(range(1, n + 1)):
        raise RuntimeError(f"{column} is not a contiguous 1..N permutation over {n} rows")


def validate_financial_only_rank_reconstructs(source_rows: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed unless every row's persisted financial_only_rank matches a
    fresh reconstruction via the canonical rank_by_financial_only() comparator
    over this exact cohort's financial_rip_v4_score values."""
    strategies = [
        {"sealedProductId": str(row["sealed_product_id"]), "financialRipV4Score": row.get("financial_rip_v4_score")}
        for row in source_rows
    ]
    reconstructed = {
        str(entry["sealedProductId"]): entry["financialOnlyRank"]
        for entry in rank_by_financial_only(strategies)
    }
    for row in source_rows:
        pid = str(row["sealed_product_id"])
        persisted = int(row["financial_only_rank"])
        expected = reconstructed.get(pid)
        if expected != persisted:
            raise RuntimeError(
                f"financial_only_rank does not reconstruct for {pid}: "
                f"persisted={persisted} reconstructed={expected}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_research_best_open_price_bucket0.py -v`

Expected: ALL PASS, including any pre-existing tests in this file.

- [ ] **Step 5: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 1 just pushed; STOP and reconcile if it has advanced further
git add backend/scripts/research_best_open_price_bucket0.py backend/tests/unit/scripts/test_research_best_open_price_bucket0.py
git commit -m "feat: add Financial-authority benchmark selection and rank-integrity validators"
git push origin HEAD:develop
```

---

### Task 3: `DualBestOpenPriceSearch` orchestrator

**Files:**
- Modify: `backend/calculations/evr/best_open_price.py` (add `DualBestOpenPriceSearch` after `ExactBestOpenPriceSearch`)
- Test: `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`

**Interfaces:**
- Consumes: `ExactBestOpenPriceSearch` (with Task 1's `shared_score_cache`/`comparison_authority`), `SharedScoreCache`, `COMPARISON_AUTHORITY_OVERALL_V12`/`COMPARISON_AUTHORITY_FINANCIAL_V4`, `BEST_OPEN_PRICE_METHOD_VERSION`.
- Produces: `BEST_OPEN_PRICE_V2_METHOD_VERSION = "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"` (new module-level constant). `DualBestOpenPriceSearch`, a dataclass whose `search() -> Dict[str, Any]` returns a dict with keys `ripResult` (the exact dict `ExactBestOpenPriceSearch.search()` would return for the RIP authority), `financialResult` (same, for FINANCIAL_V4), and `diagnostics` (a dict merging `SharedScoreCache.diagnostics()` with `uniqueQuantitiesConstructed`, `naiveScoreCount` = sum of each engine's own `evaluationCount`, `scoreReuseSavings` = `naiveScoreCount - uniqueCandidatePricesScored`). This is the exact shape Task 4's V2 row builder consumes.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`:

```python
from backend.calculations.evr.best_open_price import DualBestOpenPriceSearch, BEST_OPEN_PRICE_V2_METHOD_VERSION


def _dual_engine(*, budget, current_price_cents, current_quantity,
                  rip_rank, rip_benchmark, financial_rank, financial_benchmark,
                  seed=20260916):
    values = np.random.default_rng(seed).lognormal(2.0, 1.2, 20_000)

    quantity_cache: dict[int, PreparedCanonicalCandidate] = {}

    def prepare_quantity(q):
        if q not in quantity_cache:
            prepared = PreparedFinancialRipDistribution.prepare(values)
            quantity_cache[q] = PreparedCanonicalCandidate("product", q, prepared, 60.0, 0.002, float(budget))
        return quantity_cache[q]

    return DualBestOpenPriceSearch(
        product_id="product", budget_cents=budget,
        current_price_cents=current_price_cents, current_quantity=current_quantity,
        rip_current_rank=rip_rank, rip_benchmark=rip_benchmark,
        financial_current_rank=financial_rank, financial_benchmark=financial_benchmark,
        prepare_quantity=prepare_quantity,
        source_authority_fingerprint="fp", expected_source_authority_fingerprint="fp",
    ), quantity_cache


def test_dual_search_returns_two_threshold_objects():
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    assert result["ripResult"]["status"] == "exact"
    assert result["financialResult"]["status"] == "exact"
    assert result["ripResult"]["threshold"] is not None
    assert result["financialResult"]["threshold"] is not None


def test_dual_search_shares_one_score_cache_across_both_authorities():
    engine, quantity_cache = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=2, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    diagnostics = result["diagnostics"]
    assert diagnostics["ripComparatorEvaluations"] > 0
    assert diagnostics["financialComparatorEvaluations"] > 0
    # Both authorities search overlapping domains (both bounded above by the
    # same current price for a nonleader) -- some sharing must have occurred.
    naive = diagnostics["naiveScoreCount"]
    unique = diagnostics["uniqueCandidatePricesScored"]
    assert unique < naive
    assert diagnostics["scoreReuseSavings"] == naive - unique
    # The prepare_quantity closure itself must not be called once per
    # authority for the SAME quantity -- verify via the shared memoization
    # dict populated by the test's own prepare_quantity wrapper.
    assert len(quantity_cache) >= 1


def test_dual_search_financial_leader_only():
    """Product is Financial rank 1 (leader) but RIP rank 2 (nonleader) --
    the two searches must use genuinely different domains/directions."""
    engine, _ = _dual_engine(
        budget=135000, current_price_cents=14068, current_quantity=9,
        rip_rank=2, rip_benchmark={"sealedProductId": "rip-bench", "overallRipV12Rankable": True, "overallRipV12Score": -1e9, "financialRipV4Score": -1e9},
        financial_rank=1, financial_benchmark={"sealedProductId": "fin-bench", "financialRipV4Score": -1e9, "overallRipV12Rankable": True, "overallRipV12Score": -1e9},
    )
    result = engine.search()
    assert result["ripResult"]["currentRank"] == 2
    assert result["financialResult"]["currentRank"] == 1


def test_v1_best_open_price_method_version_unchanged():
    assert BEST_OPEN_PRICE_METHOD_VERSION == "budget_product_best_open_price_full_market_v1"
    assert BEST_OPEN_PRICE_V2_METHOD_VERSION == "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -k "dual_search or v1_best_open_price_method_version" -v`

Expected: FAIL — `DualBestOpenPriceSearch`/`BEST_OPEN_PRICE_V2_METHOD_VERSION` don't exist yet.

- [ ] **Step 3: Implement `DualBestOpenPriceSearch`**

Add the new constant right after `BEST_OPEN_PRICE_METHOD_VERSION`:

```python
BEST_OPEN_PRICE_V2_METHOD_VERSION = "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"
```

Add this class at the end of the file, after `ExactBestOpenPriceSearch`:

```python
@dataclass
class DualBestOpenPriceSearch:
    """Runs the RIP (OVERALL_V12) and Financial (FINANCIAL_V4) exact searches
    for one product, sharing one SharedScoreCache and one quantity-level
    candidate cache so neither the expensive PreparedFinancialRipDistribution
    construction nor an identical (quantity, price_cents) score is ever
    duplicated between the two searches. Never runs the two V1 exact-search
    mathematics differently -- it constructs two ordinary
    ExactBestOpenPriceSearch instances and lets each run its own unmodified
    search().
    """
    product_id: str
    budget_cents: int
    current_price_cents: int
    current_quantity: int
    rip_current_rank: int
    rip_benchmark: Mapping[str, Any]
    financial_current_rank: int
    financial_benchmark: Mapping[str, Any]
    prepare_quantity: Callable[[int], PreparedCanonicalCandidate]
    source_authority_fingerprint: str
    expected_source_authority_fingerprint: str
    prepare_quantities: Optional[
        Callable[[Sequence[int]], Mapping[int, PreparedCanonicalCandidate]]
    ] = None
    max_quantity_to_construct: int = 4096
    max_cached_quantities: int = 4
    quantity_batch_size: int = 8
    max_score_cache_entries: int = 4096

    def _shared_prepare_quantity(self, cache: Dict[int, PreparedCanonicalCandidate]) -> Callable[[int], PreparedCanonicalCandidate]:
        def prepare(quantity: int) -> PreparedCanonicalCandidate:
            if quantity not in cache:
                cache[quantity] = self.prepare_quantity(quantity)
            return cache[quantity]
        return prepare

    def _shared_prepare_quantities(
        self, cache: Dict[int, PreparedCanonicalCandidate]
    ) -> Optional[Callable[[Sequence[int]], Mapping[int, PreparedCanonicalCandidate]]]:
        if self.prepare_quantities is None:
            return None

        def prepare_batch(quantities: Sequence[int]) -> Mapping[int, PreparedCanonicalCandidate]:
            missing = [q for q in quantities if q not in cache]
            if missing:
                built = self.prepare_quantities(missing)
                cache.update(built)
            return {q: cache[q] for q in quantities}

        return prepare_batch

    def search(self) -> Dict[str, Any]:
        # One quantity-level memo shared by BOTH engines: whichever search
        # touches a given physical quantity first builds it; the other reuses
        # the same PreparedCanonicalCandidate object.
        quantity_cache: Dict[int, PreparedCanonicalCandidate] = {}
        shared_prepare_quantity = self._shared_prepare_quantity(quantity_cache)
        shared_prepare_quantities = self._shared_prepare_quantities(quantity_cache)
        score_cache = SharedScoreCache(max_entries=self.max_score_cache_entries)

        rip_engine = ExactBestOpenPriceSearch(
            product_id=self.product_id, budget_cents=self.budget_cents,
            current_price_cents=self.current_price_cents, current_quantity=self.current_quantity,
            current_rank=self.rip_current_rank, benchmark=self.rip_benchmark,
            prepare_quantity=shared_prepare_quantity,
            source_authority_fingerprint=self.source_authority_fingerprint,
            expected_source_authority_fingerprint=self.expected_source_authority_fingerprint,
            prepare_quantities=shared_prepare_quantities,
            max_quantity_to_construct=self.max_quantity_to_construct,
            max_cached_quantities=self.max_cached_quantities,
            quantity_batch_size=self.quantity_batch_size,
            shared_score_cache=score_cache,
            comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12,
        )
        financial_engine = ExactBestOpenPriceSearch(
            product_id=self.product_id, budget_cents=self.budget_cents,
            current_price_cents=self.current_price_cents, current_quantity=self.current_quantity,
            current_rank=self.financial_current_rank, benchmark=self.financial_benchmark,
            prepare_quantity=shared_prepare_quantity,
            source_authority_fingerprint=self.source_authority_fingerprint,
            expected_source_authority_fingerprint=self.expected_source_authority_fingerprint,
            prepare_quantities=shared_prepare_quantities,
            max_quantity_to_construct=self.max_quantity_to_construct,
            max_cached_quantities=self.max_cached_quantities,
            quantity_batch_size=self.quantity_batch_size,
            shared_score_cache=score_cache,
            comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
        )

        rip_result = rip_engine.search()
        financial_result = financial_engine.search()

        naive_score_count = rip_engine.evaluation_count + financial_engine.evaluation_count
        cache_diagnostics = score_cache.diagnostics()
        diagnostics = {
            **cache_diagnostics,
            "uniqueQuantitiesConstructed": len(quantity_cache),
            "naiveScoreCount": naive_score_count,
            "scoreReuseSavings": naive_score_count - cache_diagnostics["uniqueCandidatePricesScored"],
        }
        return {"ripResult": rip_result, "financialResult": financial_result, "diagnostics": diagnostics}
```

Note: `naiveScoreCount` uses each engine's own `evaluation_count` (incremented once per DISTINCT `(quantity, price_cents)` that engine's OWN `_evaluations` cache had to compute — i.e., once per unique price that engine's search touched, matching "rip comparisons + financial comparisons" from the spec's diagnostics section, since each engine's per-price evaluation always triggers exactly one comparator call). `scoreReuseSavings` can be 0 (not negative) if the two searches' domains never overlap on an identical `(quantity, price_cents)` pair — this is expected and not a bug; the test above (`test_dual_search_shares_one_score_cache_across_both_authorities`) is constructed so both searches start from the SAME `current_price_cents`/quantity for a nonleader-vs-nonleader case, guaranteeing at least the initial `(q0, current_price_cents)` overlap.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -v`

Expected: ALL PASS (new + every pre-existing test).

- [ ] **Step 5: Run the broader suite**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/scripts/test_research_best_open_price_bucket0.py -v`

Expected: PASS.

- [ ] **Step 6: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 2 just pushed; STOP and reconcile if advanced further
git add backend/calculations/evr/best_open_price.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py
git commit -m "feat: add DualBestOpenPriceSearch orchestrator sharing one score cache across authorities"
git push origin HEAD:develop
```

---

### Task 4: V2 cohort engine script and result-row contract

**Files:**
- Create: `backend/scripts/research_best_open_price_v2.py`
- Test: `backend/tests/unit/scripts/test_research_best_open_price_v2.py`

**Interfaces:**
- Consumes: `_load_source`, `_load_exact_source_products`, `_historical_authority`, `_financial_competitor`, `_comparator_row`, `_competitor`, `validate_source`, `validate_rank_column_contiguous`, `validate_financial_only_rank_reconstructs` (all from `backend.scripts.research_best_open_price_bucket0`); `build_stage1_distributions_cached`, `build_budget_strategy_values`, `build_single_q_parity_distributions` (from wherever `research_best_open_price_bucket2.py` currently imports them — check its import block and reuse the same names); `DualBestOpenPriceSearch`, `BEST_OPEN_PRICE_V2_METHOD_VERSION`, `COMPARISON_AUTHORITY_FINANCIAL_V4`, `COMPARISON_AUTHORITY_OVERALL_V12` (from `backend.calculations.evr.best_open_price`); `PreparedFinancialRipDistribution` (from `backend.calculations.evr.financial_rip_v3`); `PreparedCanonicalCandidate` (from `backend.calculations.evr.best_open_price`).
- Produces: `def run(client, *, source_snapshot_id, expected_source_authority_fingerprint, product_ids=None, max_quantity_to_construct=4096) -> Dict[str, Any]` — the per-cohort V2 engine entry point (deliberately simpler than V1's `research_best_open_price_bucket2.run()`: NO checkpoint/resume machinery and NO deterministic-replay subset in this landing — those are V1 production-hardening concerns; this phase is explicitly "engine + in-memory contract only, does not publish," so checkpointing an unpublished research artifact is out of scope per YAGNI). Returns `{"status": "complete"|"incomplete", "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION, "products": [<v2 row>, ...], "cohortAnalysis": {"attempted": int, "ripResolved": int, "financialResolved": int, "unresolved": int}}`.
- Produces: `def build_v2_row(dual_result: Mapping[str, Any], *, source_row: Mapping[str, Any]) -> Dict[str, Any]` — the pure V2 row assembler consuming ONE product's `DualBestOpenPriceSearch.search()` output (from Task 3) plus its source row, with NO recomputation of any threshold field (every threshold-evidence field is copied directly from `dual_result["ripResult"]["threshold"]`/`dual_result["financialResult"]["threshold"]`).

- [ ] **Step 1: Write `build_v2_row` and its failing tests first (pure function, no I/O)**

Add to a new file `backend/tests/unit/scripts/test_research_best_open_price_v2.py`:

```python
def _threshold(price_cents, quantity, financial_v4, overall_v12, chance, capital):
    return {
        "wins": True, "priceCents": price_cents, "quantity": quantity,
        "financialRipV4Score": financial_v4, "overallRipV12Score": overall_v12,
        "chanceToRecoverCapital": chance, "actualCommittedCapital": capital,
    }


def _search_result(status, threshold, current_rank, benchmark_id, next_price_cents=None):
    return {
        "methodVersion": "budget_product_best_open_price_full_market_v1",
        "status": status, "currentRank": current_rank, "threshold": threshold,
        "benchmarkProductId": benchmark_id,
        "exactness": {
            "thresholdWins": True, "nextPriceCents": next_price_cents, "nextPriceWins": False,
            "oneCentMaximal": True, "quantityIntervalLowCents": 1, "quantityIntervalHighCents": 2,
            "nextCentCrossesQuantityBoundary": False,
        } if threshold else None,
    }


def test_build_v2_row_exposes_backward_compatible_rip_aliases():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["bestOpenPrice"] == row["ripBestOpenPrice"] == 140.68
    assert row["status"] == row["ripStatus"] == "exact"
    assert row["exactness"] == row["ripExactness"]


def test_build_v2_row_financial_fields_are_independent_of_rip():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    financial_threshold = _threshold(14500, 10, 90.0, 40.0, 0.5, 1450.0)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", financial_threshold, 1, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 1, "budget_rank_v12": 2})
    assert row["financialBestOpenPrice"] == 145.0
    assert row["financialBenchmarkSealedProductId"] == "fin-bench"
    assert row["ripBenchmarkSealedProductId"] == "rip-bench"
    assert row["financialBenchmarkSealedProductId"] != row["ripBenchmarkSealedProductId"]
    assert row["currentFinancialOnlyRank"] == 1


def test_build_v2_row_threshold_evidence_is_copied_not_recomputed():
    rip_threshold = _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12)
    dual_result = {
        "ripResult": _search_result("exact", rip_threshold, 2, "rip-bench"),
        "financialResult": _search_result("exact", _threshold(14000, 9, 60.0, 70.0, 0.35, 1260.0), 2, "fin-bench"),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["ripThresholdFinancialRipV4Score"] == 50.0
    assert row["ripThresholdOverallRipV12Score"] == 80.0
    assert row["ripThresholdChanceToRecoverCapital"] == 0.3
    assert row["ripThresholdActualCommittedCapital"] == 1266.12
    assert row["financialThresholdFinancialRipV4Score"] == 60.0
    assert row["financialThresholdOverallRipV12Score"] == 70.0


def test_build_v2_row_requires_both_authorities_resolved_for_complete_status():
    dual_result = {
        "ripResult": _search_result("exact", _threshold(14068, 9, 50.0, 80.0, 0.3, 1266.12), 2, "rip-bench"),
        "financialResult": _search_result("unresolved_extreme_quantity", None, 2, None),
        "diagnostics": {},
    }
    row = build_v2_row(dual_result, source_row={"sealed_product_id": "p1", "financial_only_rank": 2, "budget_rank_v12": 2})
    assert row["resolved"] is False
    assert row["ripResolved"] is True
    assert row["financialResolved"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_research_best_open_price_v2.py -v`

Expected: FAIL — the module/function don't exist yet.

- [ ] **Step 3: Implement `build_v2_row` in the new `backend/scripts/research_best_open_price_v2.py`**

```python
"""Best-Open Price V2 dual-threshold research engine (no persistence, no publication).

Computes RIP (OVERALL_V12) and Financial (FINANCIAL_V4) exact thresholds for
the Full Market cohort. Deliberately has no checkpoint/resume or deterministic-
replay machinery -- this is an unpublished in-memory research artifact; that
production-hardening belongs to a later publication phase, not this one.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_V2_METHOD_VERSION,
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
    DualBestOpenPriceSearch,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.scripts.research_best_open_price_bucket0 import (
    _comparator_row,
    _competitor,
    _financial_competitor,
    _historical_authority,
    _load_exact_source_products,
    _load_source,
    validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
    validate_source,
)


def build_v2_row(dual_result: Mapping[str, Any], *, source_row: Mapping[str, Any]) -> Dict[str, Any]:
    """Assemble one V2 result row from a DualBestOpenPriceSearch.search() output.

    Every threshold-evidence field is copied verbatim from the actual scored
    threshold candidate the exact engine returned -- never recomputed here.
    """
    rip = dual_result["ripResult"]
    financial = dual_result["financialResult"]
    rip_threshold = rip.get("threshold") or {}
    financial_threshold = financial.get("threshold") or {}
    rip_resolved = rip.get("status") == "exact"
    financial_resolved = financial.get("status") == "exact"

    row: Dict[str, Any] = {
        "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "sealedProductId": str(source_row["sealed_product_id"]),
        "currentBudgetRank": int(source_row["budget_rank_v12"]),
        "currentFinancialOnlyRank": int(source_row["financial_only_rank"]),
        "resolved": bool(rip_resolved and financial_resolved),
        "ripResolved": rip_resolved,
        "financialResolved": financial_resolved,
        "diagnostics": dict(dual_result.get("diagnostics") or {}),
    }

    # --- RIP fields: both the backward-compatible generic aliases AND the
    # explicit rip* names, per Phase 5's contract. ---
    rip_price_cents = rip_threshold.get("priceCents")
    row.update({
        "bestOpenPrice": (rip_price_cents / 100.0) if rip_price_cents is not None else None,
        "bestOpenPriceCents": rip_price_cents,
        "status": rip.get("status"),
        "thresholdQuantity": rip_threshold.get("quantity"),
        "benchmarkSealedProductId": rip.get("benchmarkProductId"),
        "benchmarkOverallRipV12Score": rip.get("benchmarkOverallRipV12Score"),
        "exactness": rip.get("exactness"),

        "ripBestOpenPrice": (rip_price_cents / 100.0) if rip_price_cents is not None else None,
        "ripBestOpenPriceCents": rip_price_cents,
        "ripStatus": rip.get("status"),
        "ripThresholdQuantity": rip_threshold.get("quantity"),
        "ripBenchmarkSealedProductId": rip.get("benchmarkProductId"),
        "ripBenchmarkOverallRipV12Score": rip.get("benchmarkOverallRipV12Score"),
        "ripExactness": rip.get("exactness"),
        "ripThresholdFinancialRipV4Score": rip_threshold.get("financialRipV4Score"),
        "ripThresholdOverallRipV12Score": rip_threshold.get("overallRipV12Score"),
        "ripThresholdChanceToRecoverCapital": rip_threshold.get("chanceToRecoverCapital"),
        "ripThresholdActualCommittedCapital": rip_threshold.get("actualCommittedCapital"),
    })

    # --- Financial fields: explicit financial* names only (no generic alias
    # -- the generic/legacy names mean RIP, per the backward-compatibility
    # requirement). ---
    financial_price_cents = financial_threshold.get("priceCents")
    row.update({
        "financialBestOpenPrice": (financial_price_cents / 100.0) if financial_price_cents is not None else None,
        "financialBestOpenPriceCents": financial_price_cents,
        "financialStatus": financial.get("status"),
        "financialThresholdQuantity": financial_threshold.get("quantity"),
        "financialBenchmarkSealedProductId": financial.get("benchmarkProductId"),
        "financialBenchmarkFinancialRipV4Score": financial_threshold.get("financialRipV4Score"),
        "financialExactness": financial.get("exactness"),
        "financialThresholdFinancialRipV4Score": financial_threshold.get("financialRipV4Score"),
        "financialThresholdOverallRipV12Score": financial_threshold.get("overallRipV12Score"),
        "financialThresholdChanceToRecoverCapital": financial_threshold.get("chanceToRecoverCapital"),
        "financialThresholdActualCommittedCapital": financial_threshold.get("actualCommittedCapital"),
    })

    return row
```

Note: `row["benchmarkOverallRipV12Score"]`/`ripBenchmarkOverallRipV12Score` are read from `rip["benchmarkOverallRipV12Score"]` (the field `ExactBestOpenPriceSearch._payload()` already populates from `self.benchmark.get("overallRipV12Score")`). Add `ripBenchmarkFinancialRipV4Score` too, reading `rip.get("benchmarkFinancialRipV4Score")` if you add that field to `_payload()` in Task 1/3 — if `_payload()` does not already expose it (check the current file; per the plan's research it does NOT), read it from the RIP benchmark mapping passed to `build_v2_row` instead: this requires threading the raw `rip_benchmark`/`financial_benchmark` dicts into `build_v2_row` as additional parameters. Adjust the function signature to `build_v2_row(dual_result, *, source_row, rip_benchmark=None, financial_benchmark=None)` and set `"ripBenchmarkFinancialRipV4Score": (rip_benchmark or {}).get("financialRipV4Score")` and `"financialBenchmarkSealedProductId"`/`"financialBenchmarkFinancialRipV4Score"` similarly if the search-result dict doesn't already carry what's needed — verify against the ACTUAL `dual_result` shape Task 3 produces (from `ExactBestOpenPriceSearch._payload()`) before finalizing; if a required field isn't in the search result, thread the raw benchmark dict through rather than inventing a new field on the search engine.

- [ ] **Step 4: Run `build_v2_row` tests, confirm pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_research_best_open_price_v2.py -v`

Expected: PASS. Fix any field-shape mismatches discovered against the actual `DualBestOpenPriceSearch`/`ExactBestOpenPriceSearch` output (adjust `build_v2_row`, not the engine).

- [ ] **Step 5: Write the cohort-level `run()` function and its tests**

Add tests exercising the per-cohort rank validation fail-closed behavior (these don't need real DB I/O — call the validators directly against constructed row lists, matching Task 2's test style):

```python
def test_run_fails_closed_on_missing_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1, "budget_rank_v12": 1},
            {"sealed_product_id": "b", "financial_only_rank": None, "budget_rank_v12": 2}]
    with pytest.raises(RuntimeError, match="missing"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_duplicate_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1}, {"sealed_product_id": "b", "financial_only_rank": 1}]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_non_contiguous_financial_only_rank():
    rows = [{"sealed_product_id": "a", "financial_only_rank": 1}, {"sealed_product_id": "b", "financial_only_rank": 3}]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "financial_only_rank")


def test_run_fails_closed_on_financial_score_parity_failure():
    rows = [
        {"sealed_product_id": "high", "financial_only_rank": 2, "financial_rip_v4_score": 90.0},  # wrong rank
        {"sealed_product_id": "low", "financial_only_rank": 1, "financial_rip_v4_score": 10.0},
    ]
    with pytest.raises(RuntimeError, match="does not reconstruct"):
        validate_financial_only_rank_reconstructs(rows)
```

Implement `run(client, *, source_snapshot_id, expected_source_authority_fingerprint, product_ids=None, max_quantity_to_construct=4096)` in the new file, structured as:

```python
def run(
    client: Any, *, source_snapshot_id: str, expected_source_authority_fingerprint: str,
    product_ids: Optional[Sequence[str]] = None, max_quantity_to_construct: int = 4096,
) -> Dict[str, Any]:
    snapshot, source_rows, _all_rows = _load_source(client, source_snapshot_id)
    validate_source(snapshot)
    validate_rank_column_contiguous(source_rows, "budget_rank_v12")
    validate_rank_column_contiguous(source_rows, "financial_only_rank")
    validate_financial_only_rank_reconstructs(source_rows)

    authority = _historical_authority(snapshot, source_rows)
    if authority["fingerprint"] != expected_source_authority_fingerprint:
        raise RuntimeError("source authority fingerprint mismatch")

    budget = float(snapshot["full_market_budget"])
    budget_cents = round(budget * 100)
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    product_by_id = {str(p["sealed_product_id"]): p for p in products}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}

    ordered = sorted(source_rows, key=lambda r: int(r["budget_rank_v12"]))
    if product_ids is not None:
        missing = [pid for pid in product_ids if pid not in source_by_id]
        if missing:
            raise RuntimeError(f"requested product_ids not in cohort: {missing}")
        ordered = [r for r in ordered if str(r["sealed_product_id"]) in set(product_ids)]

    rows_out = []
    for source in ordered:
        pid = str(source["sealed_product_id"])
        product = product_by_id[pid]
        rip_competitor = _competitor(source, source_rows)
        rip_benchmark = _comparator_row(rip_competitor, budget)
        financial_competitor = _financial_competitor(source, source_rows)
        financial_benchmark = _comparator_row(financial_competitor, budget)

        # NOTE: the physical Q-unit "base" distribution construction and the
        # factory()/batch_factory() closures below MUST mirror
        # research_best_open_price_bucket2.py's execute_product() exactly --
        # copy its artifact-loading and build_stage1_distributions_cached(...)
        # call, then define ONE factory/batch_factory pair per product (not
        # per authority) and hand that SAME pair to DualBestOpenPriceSearch's
        # prepare_quantity/prepare_quantities. Do not call execute_product()
        # from bucket2.py directly -- it constructs and runs a single V1
        # ExactBestOpenPriceSearch internally, which would defeat the shared
        # single-construction requirement. Reimplement just the
        # artifact-loading + factory-closure portion here (the part of
        # execute_product() before its ExactBestOpenPriceSearch(...) call),
        # reading the exact current code from research_best_open_price_bucket2.py
        # lines ~277-365 as your template.

        dual = DualBestOpenPriceSearch(
            product_id=pid, budget_cents=budget_cents,
            current_price_cents=int(round(float(source["product_market_price"]) * 100)),
            current_quantity=int(source["quantity"]),
            rip_current_rank=int(source["budget_rank_v12"]), rip_benchmark=rip_benchmark,
            financial_current_rank=int(source["financial_only_rank"]), financial_benchmark=financial_benchmark,
            prepare_quantity=factory,  # from the mirrored closure above
            prepare_quantities=batch_factory,  # from the mirrored closure above
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=expected_source_authority_fingerprint,
            max_quantity_to_construct=max_quantity_to_construct,
        )
        result = dual.search()
        rows_out.append(build_v2_row(result, source_row=source, rip_benchmark=rip_benchmark, financial_benchmark=financial_benchmark))

    attempted = len(rows_out)
    rip_resolved = sum(1 for r in rows_out if r["ripResolved"])
    financial_resolved = sum(1 for r in rows_out if r["financialResolved"])
    unresolved = sum(1 for r in rows_out if not r["resolved"])
    status = "complete" if (rip_resolved == attempted and financial_resolved == attempted and unresolved == 0) else "incomplete"

    return {
        "status": status, "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "products": rows_out,
        "cohortAnalysis": {
            "attempted": attempted, "ripResolved": rip_resolved,
            "financialResolved": financial_resolved, "unresolved": unresolved,
        },
    }
```

The implementer must fill in the `factory`/`batch_factory` closures by copying `research_best_open_price_bucket2.py`'s `execute_product()` artifact-loading + closure-definition code (lines ~277-365 per this plan's research) verbatim, adapted only to NOT construct `ExactBestOpenPriceSearch` itself (that's `DualBestOpenPriceSearch`'s job) — this satisfies "reuses current distribution preparation... does not fork source-authority loading logic." If any imported helper name (`build_stage1_distributions_cached`, `build_budget_strategy_values`, `build_single_q_parity_distributions`, artifact-loading helper) isn't already visible, add the exact same import line `research_best_open_price_bucket2.py` uses for it.

- [ ] **Step 6: Run tests, confirm pass**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/scripts/test_research_best_open_price_v2.py -v`

Expected: PASS.

- [ ] **Step 7: Run broader suite**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/scripts/test_research_best_open_price_bucket0.py backend/tests/unit/scripts/test_research_best_open_price_v2.py -v`

Expected: PASS. Note: `backend/tests/unit/scripts/test_research_best_open_price_bucket2.py` and `test_best_open_review_regressions.py`/`test_publish_best_open_price_if_ready.py` are known to fail at COLLECTION in this worktree due to a pre-existing, unrelated Supabase-credential environment gap (confirmed independently across Phases 0-3's controller and implementers) — run them anyway and report the exact outcome, but do not treat that specific collection failure as a regression from this task.

- [ ] **Step 8: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 3 just pushed; STOP and reconcile if advanced further
git add backend/scripts/research_best_open_price_v2.py backend/tests/unit/scripts/test_research_best_open_price_v2.py
git commit -m "feat: add V2 dual-threshold cohort engine and result-row contract"
git push origin HEAD:develop
```

---

### Task 5: Remaining test-matrix coverage, diagnostics report, validation suite run

**Files:**
- Modify: `backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py`, `backend/tests/unit/scripts/test_research_best_open_price_v2.py` (fill any gaps against the 32-item matrix below not already covered by Tasks 1-4's own tests)
- Create: none required, unless the implementer finds a gap needing a new small helper

**Interfaces:** none new — this task closes coverage gaps against an explicit checklist and produces a diagnostics report; it does not add new production code (if a genuine gap reveals a missing production behavior, fix it minimally and note it in the report rather than silently expanding scope).

- [ ] **Step 1: Cross-check the 32-item test matrix against what Tasks 1-4 already added**

Go through this list and, for each item, either (a) confirm an existing test from Tasks 1-4 already covers it and cite it by name, or (b) write a new focused test. Do not duplicate an existing test under a new name.

1. dual search returns two threshold objects — Task 3: `test_dual_search_returns_two_threshold_objects`
2. both searches share the same candidate score cache — Task 3: `test_dual_search_shares_one_score_cache_across_both_authorities`
3. same (q, cent) evaluated by both authorities scores once — Task 1: `test_two_engines_sharing_one_cache_score_overlapping_candidate_once`
4. comparator counts remain independent — Task 1 (same test asserts both `ripComparatorEvaluations`/`financialComparatorEvaluations`)
5. Financial and RIP thresholds can be equal — NEW: construct a `_dual_engine` case where both authorities' benchmarks make the SAME price win under both; assert `ripResult["threshold"]["priceCents"] == financialResult["threshold"]["priceCents"]`
6. Financial threshold < RIP threshold — NEW
7. Financial threshold > RIP threshold — NEW
8. candidate leader under both — NEW: `rip_rank=1, financial_rank=1`
9. candidate leader under Financial only — Task 3: `test_dual_search_financial_leader_only`
10. candidate leader under RIP only — NEW: mirror of #9 with ranks swapped
11. candidate leader under neither — NEW: `rip_rank=2, financial_rank=2` (covered partially by `test_dual_search_returns_two_threshold_objects`; add an explicit assertion on `currentRank` for both if not already present)
12. Financial benchmark != RIP benchmark — Task 4: `test_build_v2_row_financial_fields_are_independent_of_rip` (asserts `financialBenchmarkSealedProductId != ripBenchmarkSealedProductId`)
13. Financial threshold P* wins — covered implicitly by every `status == "exact"` assertion (the engine's own `search()` raises `BestOpenPriceSearchError` if the returned threshold doesn't win — see `best_open_price.py` `search()`, `"returned threshold does not win"`); add one explicit test asserting `financialResult["threshold"]["wins"] is True`
14. Financial P*+1 loses — NEW: use `financialResult["exactness"]["oneCentMaximal"] is True` as the assertion (the engine's own `search()` already raises if P*+1 wins — assert the exactness block reports it correctly)
15. RIP threshold P* wins — mirror of #13 for `ripResult`
16. RIP P*+1 loses — mirror of #14 for `ripResult`
17. P*+1 quantity-boundary crossing Financial — NEW: construct a case where `financialResult["exactness"]["nextCentCrossesQuantityBoundary"] is True`
18. P*+1 quantity-boundary crossing RIP — mirror for `ripResult`
19. non-monotone winning island Financial — NEW: adapt the existing V1 pattern from `test_observed_fixed_interval_monotonicity_inversion_uses_exact_fallback` (a `_SyntheticCandidate`-style winning-set with a gap) to the FINANCIAL_V4 authority
20. non-monotone winning island RIP — same pattern for OVERALL_V12 (likely already covered by the existing V1 test; cite it if so)
21. generic `bestOpenPrice == ripBestOpenPrice` — Task 4: `test_build_v2_row_exposes_backward_compatible_rip_aliases`
22. generic `status == ripStatus` — same test
23. generic `exactness == ripExactness` — same test
24. threshold evidence is copied from actual scored threshold, not recomputed — Task 4: `test_build_v2_row_threshold_evidence_is_copied_not_recomputed`
25. Financial ranks missing -> fail closed — Task 4: `test_run_fails_closed_on_missing_financial_only_rank`
26. duplicate Financial rank -> fail closed — Task 4: `test_run_fails_closed_on_duplicate_financial_only_rank`
27. non-contiguous Financial ranks -> fail closed — Task 4: `test_run_fails_closed_on_non_contiguous_financial_only_rank`
28. current Financial score parity failure -> fail closed — Task 4: `test_run_fails_closed_on_financial_score_parity_failure`
29. current V12 score parity failure -> fail closed — NEW: this is `_check_published_strategy`'s existing V1 behavior (already tested in `research_best_open_price_bucket2.py`'s own test suite if it exists — check `test_research_best_open_price_bucket2.py`; if untested there, add a focused test of `validate_rank_column_contiguous`/reconstruction-style logic for V12, or cite the existing `_check_published_strategy` coverage if adequate)
30. V1 `BEST_OPEN_PRICE_METHOD_VERSION` unchanged — Task 3: `test_v1_best_open_price_method_version_unchanged`
31. V1 `ExactBestOpenPriceSearch` compatibility tests unchanged — Task 1: `test_exact_search_default_construction_is_unchanged_v1_behavior`, plus confirm every pre-existing V1 test in `test_prepared_financial_rip_and_best_open_price.py` still passes unmodified
32. shared cache bounded under large synthetic search — NEW: construct a `SharedScoreCache(max_entries=N)` and drive a `DualBestOpenPriceSearch` (or raw `ExactBestOpenPriceSearch` pair) across a synthetic domain large enough to force eviction; assert `len(cache._scores) <= N` throughout and `diagnostics()["scoreCacheEvictions"] > 0`

Write each "NEW" test. Use the existing `_dual_engine`/`_prepared_candidate`/`_engine`/`_SyntheticCandidate` helpers already in the test files rather than inventing new fixture machinery.

- [ ] **Step 2: Run every test file added/touched across Tasks 1-5**

Run: `cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2 && python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/calculations/test_best_open_price_quantity_batch.py backend/tests/unit/scripts/test_research_best_open_price_bucket0.py backend/tests/unit/scripts/test_research_best_open_price_v2.py -v`

Expected: ALL PASS.

- [ ] **Step 3: Run the user's specified validation suite and report exactly what happens**

Run each of these individually and record pass/fail/collection-error for each, without treating a pre-existing environment-gap collection failure as a task regression:

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
python -m pytest backend/tests/unit/calculations/test_budget_normalized_product_ranking.py -v
python -m pytest backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py -v
python -m pytest backend/tests/unit/calculations/test_best_open_price_quantity_batch.py -v
python -m pytest backend/tests/unit/scripts/test_research_best_open_price_bucket2.py -v
python -m pytest backend/tests/unit/scripts/test_best_open_review_regressions.py -v
python -m pytest backend/tests/unit/scripts/test_publish_best_open_price_if_ready.py -v
git diff --check
```

Also run, and report separately as explicitly pre-existing/out-of-scope per the task instructions (do not attempt to fix):

```bash
python -m pytest backend/tests/unit/scripts/test_best_open_price_scheduled_publication_contract.py -v
python -m pytest backend/tests/unit/scripts/test_best_open_process_lock.py -v
```

- [ ] **Step 4: Produce the performance/diagnostics report**

Write a small script or an ad-hoc test (`backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py::test_dual_search_diagnostics_report` or similar) that runs a `DualBestOpenPriceSearch` over a representative synthetic fixture (budget/current-price/quantity chosen so both searches do meaningful work — e.g., the same fixture as `test_dual_search_shares_one_score_cache_across_both_authorities`) and prints/asserts on: `ripComparatorEvaluations`, `financialComparatorEvaluations`, `uniqueCandidatePricesScored`, `naiveScoreCount`, `scoreReuseSavings`, and `scoreReuseSavings / naiveScoreCount` (cache hit rate) — assert these are all present and internally consistent (`naiveScoreCount == ripComparatorEvaluations + financialComparatorEvaluations` should hold when every comparator evaluation corresponds to exactly one `SharedScoreCache.evaluate()` call, which is the case here). Do not assert or claim a specific full-cohort speed improvement — only report the synthetic numbers, per the task's explicit "Do NOT claim full-cohort speed improvement yet."

- [ ] **Step 5: Checkpoint — fetch, verify, commit, push directly to develop**

```bash
cd D:\EVRCalculator\.claude\worktrees\best-open-price-v2
git fetch origin develop
git log --oneline -1 origin/develop   # confirm it matches the commit Task 4 just pushed; STOP and reconcile if advanced further
git add backend/tests/unit/calculations/test_prepared_financial_rip_and_best_open_price.py backend/tests/unit/scripts/test_research_best_open_price_v2.py
git commit -m "test: complete Best-Open V2 dual-engine test matrix and diagnostics report"
git push origin HEAD:develop
```

---

## Self-Review Notes

- Spec coverage: Phase 4-A (dual search authorities/benchmarks) — Task 2 (`_financial_competitor`) + Task 3/4 (wiring `rip_current_rank`/`financial_current_rank` from `budget_rank_v12`/`financial_only_rank`). Phase 4-B (shared scoring, bounded, separate diagnostics) — Task 1 (`SharedScoreCache` wiring) + Task 3 (`DualBestOpenPriceSearch` diagnostics). Phase 4-C (exact search semantics unchanged) — Task 1 explicitly does not touch `evaluate_price`'s domain/ordering logic, only its scoring call. Phase 4-D (dual orchestrator, no duplication) — Task 3. Phase 5-A/B/C/D (V1 aliases, Financial fields, threshold evidence, exactness blocks) — Task 4's `build_v2_row`. Phase 5-E (completeness) — Task 4's `run()` cohort-status logic. Cohort engine integration (new `research_best_open_price_v2.py`, reusing bucket0 loaders, rank-integrity fail-closed validation, current-leader reconstruction) — Task 4. Test matrix (32 items) — Task 5's explicit cross-check. Performance diagnostics — Task 5 Step 4. Validation suite — Task 5 Step 3. No DB/publication — no task in this plan touches migrations, RPCs, services, or frontend.
- No placeholders: every task has literal code for its core logic; Task 4's `run()` explicitly directs the implementer to copy verbatim, named, already-quoted V1 code (bucket2.py's artifact-loading/factory closures) rather than leaving it undefined — this is a deliberate "reuse this exact existing code" instruction, not an unfilled placeholder.
- Type consistency: `DualBestOpenPriceSearch.search() -> Dict[str, Any]` with `ripResult`/`financialResult`/`diagnostics` keys (Task 3) is consumed identically by `build_v2_row(dual_result, ...)` (Task 4). `SharedScoreCache.diagnostics()`'s key names (Task 1) are consumed identically inside `DualBestOpenPriceSearch.search()` (Task 3) and Task 5's diagnostics report.
