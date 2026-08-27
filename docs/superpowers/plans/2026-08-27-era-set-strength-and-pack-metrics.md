# Era Set Strength V1 + Era/Set Rankings-vs-Pack-Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Eras and Sets each two distinct analytical lenses — **Rankings** (relative strength) and **Pack Metrics** (one-loose-pack opening economics) — and add a new backend-published Era Set Strength V1 score that is the equal-weighted arithmetic mean of the canonical Set RIP V1 scores in each era.

**Architecture:** Two intentionally separate systems already exist in this repo and this plan must keep them separate. The **metric** hierarchy is `pokemon_rip_stats_service.py` (pooled global + per-era exact-mixture opening economics) → `/explore/opening-economics` → `OpeningEconomicsOverall` / `OpeningEconomicsEras`. The **ranking** hierarchy is `product_family_rankings_service.py` → `set_rip_service.build_set_rip` → `target["setRipV1"]` → `ExploreTableClient`. Era Set Strength V1 is a new leaf on the *ranking* side: a new pure service `backend/db/services/era_set_strength_service.py` that consumes only `target["setRipV1"].score`, attached to the rankings payload on the same read path that already attaches Set RIP, so no Opening Economics snapshot is republished. On the frontend, `ProductFamilyRankingsClient` grows a quiet secondary `SegmentedControl` under the existing primary one; the era→set drilldown carries the active lens across.

**Tech Stack:** Python 3 / pytest (backend, pure functions, no I/O in the new service); Next.js App Router + React client components; `tsx --test` for frontend `.test.mjs` / `.contract.test.mjs` files; Tailwind utility classes + `explore.module.css` / `openingEconomics.module.css`.

**Spec:** The user-supplied "Era Rankings + Set Pack Metrics — Complete Rankings/Metric Hierarchy" spec, sections 1–50, reproduced in condensed form under Global Constraints below. The full text is the authority; this plan argues from it.

## Global Constraints

These apply to **every** task. Do not restate them per task; they are implicitly part of every task's requirements.

- **Do not regress Opening Economics.** Pokémon RIP Stats v2, the exact empirical mixture methodology, equal-set weighting, pooled global + era distributions, P05/P25/P50/P75/P95/P99, Modeled Return on Spend, Entertainment Cost Share, true pooled Typical Opening and Typical Retention are all authoritative and stay byte-for-byte as published. (Spec §1, §49)
- **Do not republish or mutate the Opening Economics snapshot** to support Era rankings. Era Set Strength is computed on the *rankings* read path. (§49)
- **Public label is "Era Set Strength".** Internal contract key is `eraSetStrengthV1`. Never call it "Era RIP". (§5)
- **Methodology version string, verbatim:** `era_set_strength_v1_equal_set_mean_of_set_rip_v1` (§12)
- **The only input is `target["setRipV1"]["score"]`.** Never Overall RIP V10, Financial RIP V4, pack EV, pack metrics, product prices, raw set rank, or mean of ranks / mean of normalized ranks. (§5, §6, §38, §42)
- **Equal set weighting: one set = one vote.** Never weight by product count, family count, market value, recency, pack price, or popularity. (§6, §43)
- **No leader normalization of Era strength.** The raw mean of Set RIP scores IS the score. Format for display with the existing public score convention (score/10, one decimal). (§7)
- **Era tier derives from the Era Set Strength raw score, not from rank position.** (§8)
- **Era rank is `#N of M eras`**, descending by raw score, with M derived from the data — never hard-coded to 2. (§9)
- **Coverage is strict.** An era is rankable only when *every* public-analytics-eligible set in it carries a valid Set RIP V1 result AND it has at least 3 such sets. Otherwise `score/rank/tier = null`, `status = "unavailable"`, `statusReason = "incomplete_set_rip_coverage"`. Never average partial coverage. (§10)
- **Mixed Set RIP methodology versions must fail**, not publish a plausible number. (§14)
- **No client-side Era aggregation.** The React frontend must never `reduce`/`mean` over `setRipV1.score`. It formats and sorts published rows only. (§47)
- **Never re-rank filtered set subsets.** A set ranked #14 globally still shows #14 when the Sets lens is filtered to an era. (§36)
- **Entertainment Cost is never clamped.** Negative values are legitimate. (§30)
- **`Model Break-Even == EV`.** Never show both as separate independent statistics in the same table. (§27)
- **Public label is "Chance to Recover Cost"**, never "Chance to Profit". (§32)
- **Do not change entitlements.** Set Pack Metrics stay as public as the existing raw set metrics are today; existing paid product-level intelligence rules are untouched. (§39)
- **Defaults:** Eras defaults to **Pack Metrics**; Sets defaults to **Rankings**. (§2, §20)
- **Missing values stay missing.** Every formatter returns `null` for absent/non-finite input; never coerce to `$0.00` or `0%`. This is the existing `openingEconomicsSelector.mjs` contract.
- **Nulls sort last in both directions** for every new sortable column. (§35)
- **Cleanup at the end:** remove `.next`, test/build caches, scratch QA screenshots; inspect `git status --short`; leave only meaningful changes. No broad destructive git commands. (§50)

---

## Key Codebase Facts (read this before Task 1)

You have zero context for this codebase. These are the load-bearing facts, each verified:

**Backend — the ranking hierarchy**
- `backend/db/services/set_rip_service.py` — `build_set_rip(product_family_rankings, *, set_targets)` returns `{"methodologyVersion", "runAuthority", "rankedSetCount", "targetCount", "sets": [...]}`. Each row: `{"setId", "setName", "score", "tier", "rank", "rankable", "cohortSize", "methodologyVersion", "participatingFamilyCount", "participatingFamilies", "skuEvidenceCount", "familyScores", "displayFamilyScores"}`. `score` is on a **0–100** scale (mean standing × 100). `METHODOLOGY_VERSION = "set_rip_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit"`.
- `attach_set_rip_to_targets(targets, set_rip)` returns new target dicts with `target["setRipV1"] = row minus setId/setName`.
- `backend/rankings/public_relative.py` — `public_relative_rip_tier(score_0_to_100)` maps to S/A/B/C/D/F at 90/80/70/45/15. This is the tier function Set RIP itself uses on its 0–100 score, so **Era Set Strength uses the same function on its 0–100 mean**. `public_rip_display_score(score_0_to_100)` returns the one-decimal 0–10 public number using half-up rounding.
- `backend/desirability/public_analytics_policy.py` — `is_public_analytics_eligible(pokemon_set)` is True only for `analytics_ready`. Targets already carry a computed `target["publicAnalyticsStatus"]` string (set in `explore_rip_statistics_service.py`), and `ANALYTICS_READY` is the eligible value.
- `backend/db/services/pokemon_public_snapshot_service.py:1919` — `upgrade_rankings_set_rip_contract_if_needed(payload)` is the READ-path hook that guarantees `setRipV1` is present on served targets. It early-returns when the persisted payload is already enriched, so **it is not a safe place to add an always-runs step**. `get_pokemon_explore_rankings_snapshot_payload(limit)` (same file, ~line 1942) is the single function `/explore/rip-statistics/targets` calls.
- Targets carry `target["era"]` (era **display name**, from `eras.name`) and `target["era_id"]`. `explore_rip_statistics_service.py:1957` sets `"era": era_row.get("name") if era_row else None`.
- `backend/api/main.py:535` — `GET /explore/rip-statistics/targets` returns `get_pokemon_explore_rankings_snapshot_payload(limit)` verbatim, so any new **top-level sibling key** on that payload reaches the frontend.

**Backend — the metric hierarchy (do not touch)**
- `backend/db/services/pokemon_rip_stats_service.py` — pools exact simulated outcomes globally and per era. It groups by era **name** via `_resolve_era_names`, with `UNASSIGNED_ERA_NAME` for null FKs. Published via `GET /explore/opening-economics` (`backend/api/main.py:574`).

**Frontend**
- `frontend/app/Explore/page.js` is the shared implementation for `/Rankings` (`frontend/app/Rankings/page.js` re-exports it). It fetches targets + overall product rankings + opening economics in parallel, filters to eligible sets, sorts by `setRipV1.rank`, projects through `projectRankingsTargets`, and renders `<ProductFamilyRankingsClient targets={...} productFamilyRankings={...} initialOverallProductRankings={...} openingEconomics={...} loadError={...} />`.
- `frontend/lib/explore/ripStatisticsServer.js` `getRipStatisticsTargets()` spreads the whole backend payload (`{...cohort, targets: cohort.targets.slice(0, limit), meta: {...}}`), so a new top-level key survives to the page.
- `frontend/lib/explore/rankingsClientProjection.mjs` — **the client boundary allowlist.** `ExploreTableClient` is `"use client"`, so any target field not listed in `SCALAR_FIELDS` / `BLOCK_LEAVES` never reaches the browser. Already present and usable: `era`, `pack_cost`, `mean_value`, `median_value`, `prob_profit`, `expected_loss_when_losing`, `mean_value_to_cost_ratio`, `p95_value_to_cost_ratio`, `p99_value_to_cost_ratio`, `modelBreakEvenPrice` / `model_break_even_price`, and the whole `setRipV1` block. **`median_value_to_cost_ratio` is NOT on the target and NOT in the view** — Task 5 adds it as a backend passthrough/derivation, and Task 6 adds it to this allowlist.
- `frontend/components/explore/ProductFamilyRankingsClient.jsx` (691 lines) — owns the primary `SegmentedControl` with `options=[{economics,"Overall"},{eras,"Eras"},{sets,"Sets"},{products,"Products"}]`, the `view` state (which doubles as the product-family key), and `selectedEra` (an era **name string**) which it passes to `ExploreTableClient` as `eraFilter`. The Eras→Sets drilldown already exists: `onSelectEra={(era) => { selectView("sets"); setSelectedEra(era?.eraName || null); }}`.
- `frontend/components/explore/ExploreTableClient.jsx:521-532` filters by `String(target?.era) === eraFilter` (case-insensitive). This is the Sets **Rankings** table; do not replace it.
- `frontend/components/explore/openingEconomicsSelector.mjs` — pure formatters `money`, `ratioAsPercent`, `isAvailable`, `sortEras`, `projectEraRow`, `DEFAULT_ERA_SORT`, `UNAVAILABLE_LABEL`. **Reuse `money` and `ratioAsPercent` for Set Pack Metrics** so formatting cannot drift.
- `frontend/components/explore/OpeningEconomicsEras.jsx` (280 lines) — the existing Era Pack Metrics table + mobile cards. Preserve it; it becomes the `packMetrics` sub-lens body.
- `frontend/constants/exploreRankingConfig.mjs` exports `formatPublicRipScore(score)`.
- `frontend/components/ui/SegmentedControl.jsx` accepts `{className, ariaLabel, variant, value, onChange, mobileScroll, options}`; `variant="primary"` is the loud top-level style, `variant="pill"` is the default quieter one.
- `frontend/components/explore/RipScoreBadge.jsx` exports `RipScoreBadge` and `RipTierMark`.

**Test commands**
- Backend: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v` (run from `d:\EVRCalculator`).
- Frontend: `npx tsx --test components/explore/<File>.test.mjs` run from `d:\EVRCalculator\frontend`. Full suite: `npm run test:frontend` in `frontend/`.
- **Never run `next build` while a dev server is on :3100** — they share `frontend/.next` and corrupt each other.

---

## File Structure

**Create**
- `backend/db/services/era_set_strength_service.py` — pure Era Set Strength V1 builder + payload attach. No I/O, no Supabase client, no simulation.
- `backend/tests/unit/db/services/test_era_set_strength_service.py` — score math, equal weighting, coverage, version-mixing.
- `frontend/components/explore/eraSetStrengthSelector.mjs` — pure read/format/sort selectors for published era rows. No arithmetic that produces a statistic.
- `frontend/components/explore/eraSetStrengthSelector.test.mjs`
- `frontend/components/explore/EraRankings.jsx` — the Eras→Rankings table + mobile cards.
- `frontend/components/explore/setPackMetricsSelector.mjs` — pure read/format/sort selectors for one set's canonical one-pack metrics.
- `frontend/components/explore/setPackMetricsSelector.test.mjs`
- `frontend/components/explore/SetPackMetrics.jsx` — the Sets→Pack Metrics table + mobile cards + row disclosure.
- `frontend/components/explore/RankingsSubLens.contract.test.mjs` — frontend contract assertions for §46.

**Modify**
- `backend/db/services/explore_rip_statistics_service.py` — add `median_value_to_cost_ratio` to the target projection (Task 5).
- `backend/db/services/pokemon_public_snapshot_service.py` — call the era attach on the read path (Task 4).
- `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py` — payload-level attach test (Task 4).
- `frontend/lib/explore/rankingsClientProjection.mjs` — allowlist `median_value_to_cost_ratio` (Task 6).
- `frontend/lib/explore/rankingsClientProjection.test.mjs` — assert the new field crosses the boundary (Task 6).
- `frontend/app/Explore/page.js` — pass `eraSetStrength={payload?.eraSetStrengthV1 ?? null}` (Task 7).
- `frontend/components/explore/ProductFamilyRankingsClient.jsx` — sub-lens state, secondary control, lens-preserving drilldown, new bodies (Tasks 7, 8, 10).

Everything else is untouched. `pokemon_rip_stats_service.py`, `set_rip_service.py`, `OpeningEconomicsEras.jsx`, `OpeningEconomicsOverall.jsx` and `ExploreTableClient.jsx` are **read-only** for this pass (except `ExploreTableClient`'s existing props, which are already sufficient).

---

## Task 1: Era Set Strength V1 score math

**Files:**
- Create: `backend/db/services/era_set_strength_service.py`
- Test: `backend/tests/unit/db/services/test_era_set_strength_service.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Reads `target["setRipV1"]`, `target["era"]`, `target["era_id"]`, `target["name"]`, `target["set_id"]`/`target["target_id"]`, `target["publicAnalyticsStatus"]` — all documented above.
- Produces:
  - `METHODOLOGY_VERSION: str = "era_set_strength_v1_equal_set_mean_of_set_rip_v1"`
  - `MINIMUM_RANKABLE_SETS_PER_ERA: int = 3`
  - `build_era_set_strength(set_targets: Sequence[Mapping[str, Any]]) -> Dict[str, Any]` — returns `{"methodologyVersion", "sourceSetRipMethodologyVersion", "cohortSize", "eras": [era_contract, ...]}`; raises `ValueError` on mixed Set RIP methodology versions.

- [ ] **Step 1: Write the failing test — score is the mean of Set RIP SCORES, not ranks**

Create `backend/tests/unit/db/services/test_era_set_strength_service.py`:

```python
"""Era Set Strength V1: equal-set arithmetic mean of canonical Set RIP V1 scores."""

import pytest

from backend.db.services.era_set_strength_service import (
    METHODOLOGY_VERSION,
    MINIMUM_RANKABLE_SETS_PER_ERA,
    build_era_set_strength,
)
from backend.db.services.set_rip_service import (
    METHODOLOGY_VERSION as SET_RIP_METHODOLOGY_VERSION,
)


def target(set_id, name, era, score, *, rank=None, rankable=True,
           methodology=SET_RIP_METHODOLOGY_VERSION, status="analytics_ready"):
    """One canonical set target carrying an attached Set RIP V1 block."""
    return {
        "set_id": set_id,
        "target_id": set_id,
        "name": name,
        "era": era,
        "era_id": f"era-{era.lower().replace(' ', '-')}",
        "publicAnalyticsStatus": status,
        "setRipV1": {
            "score": score,
            "rank": rank,
            "tier": None,
            "rankable": rankable,
            "cohortSize": 6,
            "methodologyVersion": methodology,
        },
    }


def era_by_name(result, name):
    return next(era for era in result["eras"] if era["eraName"] == name)


def test_era_score_is_the_mean_of_set_rip_scores_not_of_ranks():
    """Era A holds the single best set AND the single worst; Era B is uniformly
    mid. Mean-of-RANK would put A ahead (ranks 1,2,6 -> 3.0 vs 3,4,5 -> 4.0);
    mean-of-SCORE correctly puts B ahead (73.0 vs 90,89,40 -> 73.0... no):
    A = (90+89+40)/3 = 73.0, B = (75+74+73)/3 = 74.0. B wins on magnitude."""
    targets = [
        target("a1", "A One", "Era A", 90.0, rank=1),
        target("a2", "A Two", "Era A", 89.0, rank=2),
        target("a3", "A Three", "Era A", 40.0, rank=6),
        target("b1", "B One", "Era B", 75.0, rank=3),
        target("b2", "B Two", "Era B", 74.0, rank=4),
        target("b3", "B Three", "Era B", 73.0, rank=5),
    ]

    result = build_era_set_strength(targets)

    assert era_by_name(result, "Era A")["score"] == pytest.approx(73.0)
    assert era_by_name(result, "Era B")["score"] == pytest.approx(74.0)
    # The rank ordering follows the SCORE, so the mean-of-rank answer loses.
    assert era_by_name(result, "Era B")["rank"] == 1
    assert era_by_name(result, "Era A")["rank"] == 2
    assert era_by_name(result, "Era A")["cohortSize"] == 2
    assert result["methodologyVersion"] == METHODOLOGY_VERSION
    assert result["sourceSetRipMethodologyVersion"] == SET_RIP_METHODOLOGY_VERSION


def test_public_score_is_the_raw_score_on_the_zero_to_ten_scale():
    """No leader normalization: the top era is NOT forced to 10.0."""
    targets = [
        target("a1", "A One", "Era A", 90.0),
        target("a2", "A Two", "Era A", 89.0),
        target("a3", "A Three", "Era A", 40.0),
        target("b1", "B One", "Era B", 75.0),
        target("b2", "B Two", "Era B", 74.0),
        target("b3", "B Three", "Era B", 73.0),
    ]

    result = build_era_set_strength(targets)

    leader = era_by_name(result, "Era B")
    assert leader["publicScore"] == pytest.approx(7.4)
    assert leader["publicScore"] != 10.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.db.services.era_set_strength_service'`

- [ ] **Step 3: Write the implementation**

Create `backend/db/services/era_set_strength_service.py`:

```python
"""Era Set Strength V1 — equal-set arithmetic mean of canonical Set RIP V1 scores.

WHAT THIS IS, AND WHAT IT IS DELIBERATELY NOT
---------------------------------------------
This is the top leaf of the RANKING hierarchy:

    product family rankings -> Set RIP V1 -> Era Set Strength V1

It answers "which era contains the strongest sets overall?". It is NOT the Era
Opening Economics lens, which answers "what does opening one loose pack from
this era look like?" and is produced by an entirely separate engine
(`pokemon_rip_stats_service.py`, exact empirical mixture over pooled simulated
outcomes). The two never feed each other: no pooled opening statistic enters a
score here, and nothing here enters a pooled opening statistic.

THE ONLY INPUT IS `target["setRipV1"]["score"]`
-----------------------------------------------
Not Overall RIP V10, not Financial RIP V4, not pack EV, not pack price, not
popularity, and NOT the set's rank. Set RIP V1 is already the canonical summary
of how a set's sealed-product ecosystem stands across product-family cohorts,
and it preserves MAGNITUDE. Averaging ranks would discard exactly the
information the score exists to carry: an era holding the #1 and #2 sets plus a
weak one is not obviously stronger than an era of three solid sets, and only the
scores can say which.

EVERY SET IS ONE VOTE
---------------------
No weighting by product count, supported family count, market value, release
recency, pack price or popularity. Set RIP V1 has already summarized the set;
weighting again here would double-count the same evidence.

NO SECOND RELATIVE TRANSFORM
----------------------------
The raw mean IS the score. The leader is not curved to 10.0. Set RIP is already
a relative standing, and leader-normalizing a mean of relative standings would
say more about the cohort's shape than about any era. `publicScore` is the same
raw number on the public 0-10 scale, through the SAME rounding helper every
other public RIP score uses.

COVERAGE FAILS CLOSED
---------------------
An era is rankable only when EVERY public-analytics-eligible set in it carries a
valid Set RIP V1 result, and only when it has at least three of them. A future
era holding one or two modeled sets would otherwise publish a confident-looking
score built from almost nothing.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, Mapping, Optional, Sequence

from backend.db.services.set_rip_service import (
    METHODOLOGY_VERSION as SET_RIP_METHODOLOGY_VERSION,
)
from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.rankings.public_relative import (
    public_relative_rip_tier,
    public_rip_display_score,
)

METHODOLOGY_VERSION = "era_set_strength_v1_equal_set_mean_of_set_rip_v1"

#: An era needs at least this many rankable sets before it receives an official
#: Era Set Strength score, rank and tier. Two modeled sets can be an accident of
#: what has been simulated so far; three is the smallest cohort where the mean
#: describes the era rather than a coincidence.
MINIMUM_RANKABLE_SETS_PER_ERA = 3

UNASSIGNED_ERA_NAME = "Unassigned"

STATUS_RANKED = "ranked"
STATUS_UNAVAILABLE = "unavailable"
REASON_INCOMPLETE_COVERAGE = "incomplete_set_rip_coverage"
REASON_INSUFFICIENT_SETS = "insufficient_rankable_sets"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _set_id(target: Mapping[str, Any]) -> str:
    return _text(target.get("set_id") or target.get("target_id"))


def _era_name(target: Mapping[str, Any]) -> str:
    return _text(target.get("era")) or UNASSIGNED_ERA_NAME


def build_era_set_strength(set_targets: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the Era Set Strength V1 contract from Set-RIP-attached targets.

    `set_targets` must be the SAME authoritative target list the Rankings cohort
    is served from, with `setRipV1` already attached. Mixed Set RIP methodology
    versions raise rather than publishing a plausible-looking era number built
    from two different models.
    """
    eligible = [target for target in set_targets
                if is_public_analytics_eligible(target) and _set_id(target)]

    versions = {
        _text((target.get("setRipV1") or {}).get("methodologyVersion"))
        for target in eligible
        if (target.get("setRipV1") or {}).get("methodologyVersion") is not None
    }
    unexpected = versions - {SET_RIP_METHODOLOGY_VERSION}
    if unexpected:
        raise ValueError(
            "Era Set Strength requires one canonical Set RIP methodology; "
            f"found {sorted(unexpected)} alongside {SET_RIP_METHODOLOGY_VERSION}"
        )

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for target in eligible:
        grouped[_era_name(target)].append(target)

    eras: list[Dict[str, Any]] = []
    for era_name in sorted(grouped):
        members = grouped[era_name]
        constituents = []
        rankable_scores: list[float] = []
        for target in sorted(members, key=lambda row: _text(row.get("name"))):
            block = target.get("setRipV1") or {}
            score = _optional_float(block.get("score"))
            usable = bool(block.get("rankable")) and score is not None
            if usable:
                rankable_scores.append(score)
            constituents.append({
                "setId": _set_id(target),
                "setName": target.get("name"),
                "setRipScore": score,
                "setRipRank": block.get("rank"),
                "setRipTier": block.get("tier"),
            })

        eligible_count = len(members)
        rankable_count = len(rankable_scores)
        coverage_complete = rankable_count == eligible_count and eligible_count > 0

        if not coverage_complete:
            status, reason, score = STATUS_UNAVAILABLE, REASON_INCOMPLETE_COVERAGE, None
        elif rankable_count < MINIMUM_RANKABLE_SETS_PER_ERA:
            status, reason, score = STATUS_UNAVAILABLE, REASON_INSUFFICIENT_SETS, None
        else:
            status, reason = STATUS_RANKED, None
            score = round(statistics.fmean(rankable_scores), 6)

        eras.append({
            "methodologyVersion": METHODOLOGY_VERSION,
            "sourceSetRipMethodologyVersion": SET_RIP_METHODOLOGY_VERSION,
            "eraId": _text(members[0].get("era_id")) or None,
            "eraName": era_name,
            "score": score,
            "publicScore": public_rip_display_score(score),
            "rank": None,
            "cohortSize": 0,
            "tier": public_relative_rip_tier(score),
            "eligibleSetCount": eligible_count,
            "rankableSetCount": rankable_count,
            "coverageComplete": coverage_complete,
            "status": status,
            "statusReason": reason,
            "constituentSets": constituents,
        })

    ranked = sorted((era for era in eras if era["status"] == STATUS_RANKED),
                    key=lambda era: (-era["score"], era["eraName"]))
    cohort_size = len(ranked)
    for position, era in enumerate(ranked, 1):
        era["rank"] = position
    for era in eras:
        era["cohortSize"] = cohort_size

    unranked = sorted((era for era in eras if era["status"] != STATUS_RANKED),
                      key=lambda era: era["eraName"])
    return {
        "methodologyVersion": METHODOLOGY_VERSION,
        "sourceSetRipMethodologyVersion": SET_RIP_METHODOLOGY_VERSION,
        "minimumRankableSetsPerEra": MINIMUM_RANKABLE_SETS_PER_ERA,
        "cohortSize": cohort_size,
        "eras": ranked + unranked,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/era_set_strength_service.py backend/tests/unit/db/services/test_era_set_strength_service.py
git commit -m "feat(rankings): Era Set Strength V1 equal-set mean of Set RIP V1 scores"
```

---

## Task 2: Era Set Strength coverage, weighting and version rules

**Files:**
- Modify: `backend/tests/unit/db/services/test_era_set_strength_service.py` (append)
- Modify: `backend/db/services/era_set_strength_service.py` only if a test fails

**Interfaces:**
- Consumes: `build_era_set_strength`, `METHODOLOGY_VERSION`, `MINIMUM_RANKABLE_SETS_PER_ERA` from Task 1.
- Produces: nothing new. This task pins behaviour Task 1 already implemented, per spec §43 and §44.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/db/services/test_era_set_strength_service.py`:

```python
def test_equal_set_weighting_ignores_product_and_family_counts():
    """One set = one vote. A set with 4 families and 30 SKUs must not outweigh
    a set with 2 families and 4 SKUs."""
    heavy = target("a1", "A One", "Era A", 40.0)
    heavy["setRipV1"].update({"participatingFamilyCount": 4, "skuEvidenceCount": 30})
    light_one = target("a2", "A Two", "Era A", 100.0)
    light_one["setRipV1"].update({"participatingFamilyCount": 2, "skuEvidenceCount": 4})
    light_two = target("a3", "A Three", "Era A", 100.0)
    light_two["setRipV1"].update({"participatingFamilyCount": 2, "skuEvidenceCount": 4})

    result = build_era_set_strength([heavy, light_one, light_two])

    # Unweighted: (40 + 100 + 100) / 3 = 80.0. SKU-weighted would be 62.1.
    assert era_by_name(result, "Era A")["score"] == pytest.approx(80.0)


def test_complete_era_is_rankable_and_carries_a_score_derived_tier():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0),
    ]

    era = era_by_name(build_era_set_strength(targets), "Era A")

    assert era["status"] == "ranked"
    assert era["statusReason"] is None
    assert era["coverageComplete"] is True
    assert era["eligibleSetCount"] == 3
    assert era["rankableSetCount"] == 3
    assert era["score"] == pytest.approx(92.0)
    # 92.0 lands in the S band (>= 90) of the SHARED public tier function. The
    # tier follows the score, never the #1 position.
    assert era["tier"] == "S"


def test_top_ranked_era_is_not_automatically_s_tier():
    """Rank is cohort placement; tier is score strength. They must not be
    conflated: the best of a weak cohort is still a weak era."""
    targets = [
        target("a1", "A One", "Era A", 50.0),
        target("a2", "A Two", "Era A", 50.0),
        target("a3", "A Three", "Era A", 50.0),
        target("b1", "B One", "Era B", 20.0),
        target("b2", "B Two", "Era B", 20.0),
        target("b3", "B Three", "Era B", 20.0),
    ]

    era = era_by_name(build_era_set_strength(targets), "Era A")

    assert era["rank"] == 1
    assert era["tier"] == "C"


def test_one_missing_set_rip_result_makes_the_whole_era_unavailable():
    """Averaging whatever happened to be available and presenting it as complete
    is the exact failure this rule exists to prevent."""
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0),
        target("a4", "A Four", "Era A", None, rankable=False),
    ]

    era = era_by_name(build_era_set_strength(targets), "Era A")

    assert era["status"] == "unavailable"
    assert era["statusReason"] == "incomplete_set_rip_coverage"
    assert era["score"] is None
    assert era["publicScore"] is None
    assert era["rank"] is None
    assert era["tier"] is None
    assert era["coverageComplete"] is False
    assert era["eligibleSetCount"] == 4
    assert era["rankableSetCount"] == 3


def test_fewer_than_three_sets_is_unavailable_even_with_complete_coverage():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
    ]

    era = era_by_name(build_era_set_strength(targets), "Era A")

    assert era["coverageComplete"] is True
    assert era["status"] == "unavailable"
    assert era["statusReason"] == "insufficient_rankable_sets"
    assert era["score"] is None
    assert MINIMUM_RANKABLE_SETS_PER_ERA == 3


def test_mixed_set_rip_methodology_versions_refuse_to_publish():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0, methodology="set_rip_v0_legacy"),
    ]

    with pytest.raises(ValueError, match="canonical Set RIP methodology"):
        build_era_set_strength(targets)


def test_sets_withheld_from_public_analytics_are_not_part_of_any_era_cohort():
    """A hidden-pending-validation set must neither be counted as missing
    coverage nor contribute a score — it is not in the public cohort at all."""
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0),
        target("a4", "A Four", "Era A", None, rankable=False,
               status="hidden_pending_validation"),
    ]

    era = era_by_name(build_era_set_strength(targets), "Era A")

    assert era["eligibleSetCount"] == 3
    assert era["coverageComplete"] is True
    assert era["status"] == "ranked"
    assert [row["setId"] for row in era["constituentSets"]] == ["a1", "a2", "a3"]


def test_cohort_size_counts_only_ranked_eras_and_is_not_hard_coded():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0),
        target("b1", "B One", "Era B", 75.0),
        target("b2", "B Two", "Era B", 74.0),
        target("b3", "B Three", "Era B", 73.0),
        target("c1", "C One", "Era C", 60.0),
        target("c2", "C Two", "Era C", 59.0),
        target("c3", "C Three", "Era C", 58.0),
    ]

    result = build_era_set_strength(targets)

    assert result["cohortSize"] == 3
    assert [era["rank"] for era in result["eras"]] == [1, 2, 3]
    assert all(era["cohortSize"] == 3 for era in result["eras"])
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v`
Expected: all PASS. If `test_sets_withheld_from_public_analytics_are_not_part_of_any_era_cohort` fails, the cause is `is_public_analytics_eligible` reading `publicAnalyticsStatus` differently than assumed — in that case change `build_era_set_strength`'s `eligible` filter to:

```python
    eligible = [target for target in set_targets
                if _text(target.get("publicAnalyticsStatus")) == "analytics_ready"
                and _set_id(target)]
```

and drop the `is_public_analytics_eligible` import. That is the only permitted edit in this step.

- [ ] **Step 3: Run the whole backend service test file once more**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v`
Expected: 10 passed

- [ ] **Step 4: Commit**

```bash
git add backend/db/services/era_set_strength_service.py backend/tests/unit/db/services/test_era_set_strength_service.py
git commit -m "test(rankings): pin Era Set Strength coverage, weighting and version rules"
```

---

## Task 3: Compact era payload attach

**Files:**
- Modify: `backend/db/services/era_set_strength_service.py`
- Modify: `backend/tests/unit/db/services/test_era_set_strength_service.py` (append)

**Interfaces:**
- Consumes: `build_era_set_strength` (Task 1).
- Produces: `attach_era_set_strength_to_payload(payload: Mapping[str, Any]) -> Dict[str, Any]` — returns a NEW payload dict with `payload["eraSetStrengthV1"]` set. Never mutates its argument. On any failure it returns the payload with `eraSetStrengthV1` set to an explicit unavailable contract, never raising into the read path.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/db/services/test_era_set_strength_service.py`:

```python
from backend.db.services.era_set_strength_service import (
    attach_era_set_strength_to_payload,
)


def _payload(targets):
    return {"targets": targets, "meta": {"request": {"limit": 60}}}


def test_attach_publishes_a_compact_top_level_block():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0),
    ]
    payload = _payload(targets)

    attached = attach_era_set_strength_to_payload(payload)

    block = attached["eraSetStrengthV1"]
    assert block["methodologyVersion"] == METHODOLOGY_VERSION
    assert block["status"] == "available"
    assert len(block["eras"]) == 1
    # The original payload is untouched — the read path shares this object.
    assert "eraSetStrengthV1" not in payload
    # Targets are NOT duplicated inside the era block: constituents are compact.
    constituent = block["eras"][0]["constituentSets"][0]
    assert set(constituent) == {"setId", "setName", "setRipScore", "setRipRank", "setRipTier"}


def test_attach_reports_unavailable_instead_of_raising_on_mixed_versions():
    targets = [
        target("a1", "A One", "Era A", 95.0),
        target("a2", "A Two", "Era A", 92.0),
        target("a3", "A Three", "Era A", 89.0, methodology="set_rip_v0_legacy"),
    ]

    block = attach_era_set_strength_to_payload(_payload(targets))["eraSetStrengthV1"]

    assert block["status"] == "unavailable"
    assert block["reason"] == "set_rip_methodology_mismatch"
    assert block["eras"] == []


def test_attach_reports_unavailable_when_the_payload_has_no_targets():
    block = attach_era_set_strength_to_payload({"meta": {}})["eraSetStrengthV1"]

    assert block["status"] == "unavailable"
    assert block["reason"] == "no_targets"
    assert block["eras"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v -k attach`
Expected: FAIL — `ImportError: cannot import name 'attach_era_set_strength_to_payload'`

- [ ] **Step 3: Implement the attach**

Append to `backend/db/services/era_set_strength_service.py`:

```python
def _unavailable(reason: str) -> Dict[str, Any]:
    return {
        "methodologyVersion": METHODOLOGY_VERSION,
        "sourceSetRipMethodologyVersion": SET_RIP_METHODOLOGY_VERSION,
        "status": "unavailable",
        "reason": reason,
        "cohortSize": 0,
        "eras": [],
    }


def attach_era_set_strength_to_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach `eraSetStrengthV1` as a TOP-LEVEL sibling of the rankings payload.

    SAME RUN AUTHORITY BY CONSTRUCTION. It reads the payload's own target list —
    the one Rankings is served from, with `setRipV1` already attached — rather
    than independently re-fetching "the latest Set RIP rows", so the era numbers
    can never describe a different cohort than the Sets lens shows.

    It is a TOP-LEVEL sibling, not a per-target key, for the same reason
    `setRip` is: an era is a partition of the cohort, and nesting a whole era
    contract under each of its member sets would ship the same block N times
    across the RSC boundary.

    NEVER RAISES. A ranking failure must not take the Rankings page down with
    it; an explicit unavailable contract is served instead, exactly as
    `/explore/opening-economics` does for its own lens.
    """
    targets = payload.get("targets") if isinstance(payload, Mapping) else None
    if not isinstance(targets, list) or not targets:
        return {**(payload if isinstance(payload, Mapping) else {}),
                "eraSetStrengthV1": _unavailable("no_targets")}
    try:
        built = build_era_set_strength(targets)
    except ValueError:
        logger.warning("[era-set-strength] refusing to publish mixed Set RIP methodologies",
                       exc_info=True)
        return {**payload, "eraSetStrengthV1": _unavailable("set_rip_methodology_mismatch")}
    except Exception:
        logger.exception("[era-set-strength] build failed; serving unavailable")
        return {**payload, "eraSetStrengthV1": _unavailable("build_failed")}
    return {**payload, "eraSetStrengthV1": {**built, "status": "available", "reason": None}}
```

Add near the top of the same file, after the imports:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest backend/tests/unit/db/services/test_era_set_strength_service.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/era_set_strength_service.py backend/tests/unit/db/services/test_era_set_strength_service.py
git commit -m "feat(rankings): attach eraSetStrengthV1 to the rankings payload without raising"
```

---

## Task 4: Serve Era Set Strength from the rankings read path

**Files:**
- Modify: `backend/db/services/pokemon_public_snapshot_service.py` (imports, and the return of `get_pokemon_explore_rankings_snapshot_payload`)
- Test: `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py` (append)

**Interfaces:**
- Consumes: `attach_era_set_strength_to_payload` (Task 3), `upgrade_rankings_set_rip_contract_if_needed` (existing, same file).
- Produces: every payload returned by `get_pokemon_explore_rankings_snapshot_payload` carries a top-level `eraSetStrengthV1`, which `GET /explore/rip-statistics/targets` returns verbatim.

- [ ] **Step 1: Read the current function before editing**

Run: `sed -n '1919,2010p' backend/db/services/pokemon_public_snapshot_service.py`

Identify **every** `return` statement in `get_pokemon_explore_rankings_snapshot_payload` (including the stale-fallback branches). The attach must wrap the value at each return, or — preferably — the function's body should be renamed and wrapped once. Use the wrapper approach below; it cannot miss a branch.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py`:

```python
def test_rankings_payload_always_carries_era_set_strength(monkeypatch):
    """Every served rankings payload — fresh, upgraded or stale-fallback —
    exposes the era block, because /explore/rip-statistics/targets returns this
    payload verbatim and the frontend is forbidden from aggregating eras."""
    from backend.db.services import pokemon_public_snapshot_service as service

    served = {
        "targets": [
            {"set_id": "a1", "target_id": "a1", "name": "A One", "era": "Era A",
             "era_id": "era-a", "publicAnalyticsStatus": "analytics_ready",
             "setRipV1": {"score": 95.0, "rank": 1, "tier": "S", "rankable": True,
                          "cohortSize": 3, "methodologyVersion": SET_RIP_METHODOLOGY_VERSION}},
            {"set_id": "a2", "target_id": "a2", "name": "A Two", "era": "Era A",
             "era_id": "era-a", "publicAnalyticsStatus": "analytics_ready",
             "setRipV1": {"score": 92.0, "rank": 2, "tier": "S", "rankable": True,
                          "cohortSize": 3, "methodologyVersion": SET_RIP_METHODOLOGY_VERSION}},
            {"set_id": "a3", "target_id": "a3", "name": "A Three", "era": "Era A",
             "era_id": "era-a", "publicAnalyticsStatus": "analytics_ready",
             "setRipV1": {"score": 89.0, "rank": 3, "tier": "A", "rankable": True,
                          "cohortSize": 3, "methodologyVersion": SET_RIP_METHODOLOGY_VERSION}},
        ],
        "meta": {},
    }
    monkeypatch.setattr(service, "_build_rankings_snapshot_payload", lambda limit: served)

    payload = service.get_pokemon_explore_rankings_snapshot_payload(limit=60)

    block = payload["eraSetStrengthV1"]
    assert block["status"] == "available"
    assert block["eras"][0]["eraName"] == "Era A"
    assert block["eras"][0]["rank"] == 1
```

Add at the top of that test file, alongside the existing imports:

```python
from backend.db.services.set_rip_service import (
    METHODOLOGY_VERSION as SET_RIP_METHODOLOGY_VERSION,
)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py -v -k era_set_strength`
Expected: FAIL — `AttributeError: ... has no attribute '_build_rankings_snapshot_payload'`

- [ ] **Step 4: Rename the existing function and add the wrapper**

In `backend/db/services/pokemon_public_snapshot_service.py`:

1. Add to the imports near line 20:

```python
from backend.db.services.era_set_strength_service import attach_era_set_strength_to_payload
```

2. Rename the existing public function `def get_pokemon_explore_rankings_snapshot_payload(limit: Any = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:` to `def _build_rankings_snapshot_payload(limit: Any = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:`, leaving its body **completely unchanged**.

3. Immediately after that function's body ends, add the new public wrapper:

```python
def get_pokemon_explore_rankings_snapshot_payload(limit: Any = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:
    """Serve the rankings payload with Era Set Strength V1 attached.

    A WRAPPER, NOT A BRANCH. `_build_rankings_snapshot_payload` returns from
    several places — the fresh read, the Set RIP compatibility upgrade, and two
    stale-cache fallbacks — and an era block attached at only some of them would
    make the Eras lens blink out exactly when the page was already degraded.
    Wrapping once cannot miss a branch.

    Nothing about the persisted snapshot changes: this is a READ-path
    enrichment, so no Opening Economics or Rankings snapshot is republished to
    support era rankings.
    """
    return attach_era_set_strength_to_payload(_build_rankings_snapshot_payload(limit))
```

4. Search for internal callers of the old name inside this file and repoint any that should skip the enrichment: run `grep -n "get_pokemon_explore_rankings_snapshot_payload" backend/db/services/pokemon_public_snapshot_service.py`. Callers **outside** this file must keep calling the public name and therefore get the enrichment; leave them alone.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py -v`
Expected: all PASS, including the pre-existing tests.

- [ ] **Step 6: Run the broader backend ranking suites for regressions**

Run: `python -m pytest backend/tests/unit/db/services/test_set_rip_service.py backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py backend/tests/unit/scripts/test_rip_leaderboard_history_contract.py -v`
Expected: all PASS. Report the actual output; do not claim success without it.

- [ ] **Step 7: Commit**

```bash
git add backend/db/services/pokemon_public_snapshot_service.py backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py
git commit -m "feat(rankings): serve eraSetStrengthV1 on every rankings read-path branch"
```

---

## Task 5: Publish `median_value_to_cost_ratio` on set targets

**Files:**
- Modify: `backend/db/services/explore_rip_statistics_service.py` (~line 2016, the target projection block)
- Test: `backend/tests/unit/db/services/` — add to the existing explore rip statistics test module if one exists; otherwise create `backend/tests/unit/db/services/test_explore_rip_statistics_typical_retention.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `target["median_value_to_cost_ratio"]` — a float or `None` — on every set target. Task 6 ships it to the client; Task 9 renders it as Typical Retention.

**Why this task exists:** spec §31 prefers the canonical `median_value_to_cost_ratio`. It is computed in `backend/calculations/evr/derived_metrics.py:1352` as `_safe_ratio(median_value, pack_cost)` but is **not** projected onto the Rankings target and **not** in the `explore_rip_statistics_latest` view. Deriving it once here — in the backend read contract, next to the existing `_resolve_mean_value_to_cost_ratio` — is what §29/§31 permit, and keeps the derivation out of React entirely.

- [ ] **Step 1: Read the existing sibling resolver**

Run: `sed -n '445,460p' backend/db/services/explore_rip_statistics_service.py`

You will see `_resolve_mean_value_to_cost_ratio(row)`: it reads the published `mean_value_to_cost_ratio` and falls back to `mean_value / pack_cost` when `pack_cost > 0`. Mirror it exactly.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/db/services/test_explore_rip_statistics_typical_retention.py`:

```python
"""Typical Retention's source ratio, resolved once in the backend read contract."""

import pytest

from backend.db.services.explore_rip_statistics_service import (
    _resolve_median_value_to_cost_ratio,
)


def test_published_ratio_is_preferred_over_derivation():
    row = {"median_value_to_cost_ratio": 0.61, "median_value": 1.84, "pack_cost": 4.05}
    assert _resolve_median_value_to_cost_ratio(row) == pytest.approx(0.61)


def test_ratio_is_derived_once_when_the_column_is_absent():
    row = {"median_value": 1.84, "pack_cost": 4.05}
    assert _resolve_median_value_to_cost_ratio(row) == pytest.approx(1.84 / 4.05)


def test_missing_or_zero_pack_cost_stays_unavailable():
    """A fabricated 0% is indistinguishable from a measured one."""
    assert _resolve_median_value_to_cost_ratio({"median_value": 1.84, "pack_cost": 0}) is None
    assert _resolve_median_value_to_cost_ratio({"median_value": 1.84}) is None
    assert _resolve_median_value_to_cost_ratio({"pack_cost": 4.05}) is None
    assert _resolve_median_value_to_cost_ratio({}) is None
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_explore_rip_statistics_typical_retention.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_median_value_to_cost_ratio'`

- [ ] **Step 4: Implement**

Add to `backend/db/services/explore_rip_statistics_service.py`, immediately after `_resolve_mean_value_to_cost_ratio`:

```python
def _resolve_median_value_to_cost_ratio(row: Dict[str, Any]) -> Optional[float]:
    """Typical Retention's source ratio: P50 opening value / current pack price.

    Derived HERE, once, rather than in React. `median_value_to_cost_ratio` is a
    real canonical metric (derived_metrics.py computes it as
    `_safe_ratio(median_value, pack_cost)`), but it is not carried on the
    `explore_rip_statistics_latest` row this projection reads, so the published
    column is preferred when present and the identical ratio is reconstructed
    from the SAME row's `median_value` and `pack_cost` when it is not. Both
    numbers come from one simulation run, so this can never mix a median from
    one run with a price from another.

    It is NOT Modeled Return. Modeled Return is mean/price (long-run average);
    this is median/price (what a typical single opening returns). Blurring them
    would make a right-skewed set look typical when it is not.
    """
    ratio = _to_optional_float(row.get("median_value_to_cost_ratio"))
    if ratio is not None:
        return ratio
    median_value = _to_optional_float(row.get("median_value"))
    pack_cost = _to_optional_float(row.get("pack_cost"))
    if median_value is None or pack_cost is None or pack_cost <= 0:
        return None
    return median_value / pack_cost
```

Then in the target projection block, immediately after the existing `"median_value": row.get("median_value"),` line (~2016), add:

```python
                # Typical Retention's source ratio. Resolved once here so no
                # React component divides a median by a price.
                "median_value_to_cost_ratio": _resolve_median_value_to_cost_ratio(row),
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest backend/tests/unit/db/services/test_explore_rip_statistics_typical_retention.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/db/services/explore_rip_statistics_service.py backend/tests/unit/db/services/test_explore_rip_statistics_typical_retention.py
git commit -m "feat(rankings): resolve median_value_to_cost_ratio once in the target read contract"
```

---

## Task 6: Ship the new field across the client boundary

**Files:**
- Modify: `frontend/lib/explore/rankingsClientProjection.mjs` (the `SCALAR_FIELDS` array)
- Modify: `frontend/lib/explore/rankingsClientProjection.test.mjs`

**Interfaces:**
- Consumes: `target["median_value_to_cost_ratio"]` (Task 5).
- Produces: `projectRankingsTargets` output rows carry `median_value_to_cost_ratio`. Task 9's selectors read it.

- [ ] **Step 1: Write the failing test**

Append to `frontend/lib/explore/rankingsClientProjection.test.mjs`:

```javascript
test("projects median_value_to_cost_ratio for the Set Pack Metrics lens", () => {
  // Typical Retention is a PRIMARY column of Sets -> Pack Metrics. A field the
  // projection drops is silently null in the browser, which renders as
  // "Unavailable" with no error anywhere — so the boundary is pinned by test.
  const [projected] = projectRankingsTargets([
    { set_id: "sv3pt5", name: "151", median_value_to_cost_ratio: 0.4543 },
  ]);

  assert.equal(projected.median_value_to_cost_ratio, 0.4543);
  assert.ok(RANKINGS_CLIENT_FIELDS.includes("median_value_to_cost_ratio"));
});
```

If the file's existing imports do not already bring in `RANKINGS_CLIENT_FIELDS`, add it to the existing import statement from `./rankingsClientProjection.mjs`.

- [ ] **Step 2: Run to verify it fails**

Run from `d:\EVRCalculator\frontend`: `npx tsx --test lib/explore/rankingsClientProjection.test.mjs`
Expected: FAIL — `projected.median_value_to_cost_ratio` is `undefined`

- [ ] **Step 3: Implement**

In `frontend/lib/explore/rankingsClientProjection.mjs`, in `SCALAR_FIELDS`, immediately after the `"mean_value_to_cost_ratio", "mean_value_to_cost_rank", "mean_value_to_cost_tier",` line, add:

```javascript
  // Typical Retention (P50 / pack price) for Sets -> Pack Metrics. Resolved in
  // the backend read contract (explore_rip_statistics_service), never derived
  // in a component.
  "median_value_to_cost_ratio",
```

- [ ] **Step 4: Run the test**

Run from `frontend`: `npx tsx --test lib/explore/rankingsClientProjection.test.mjs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/explore/rankingsClientProjection.mjs frontend/lib/explore/rankingsClientProjection.test.mjs
git commit -m "feat(rankings): project median_value_to_cost_ratio across the client boundary"
```

---

## Task 7: Secondary lens control with lens-preserving drilldown

**Files:**
- Modify: `frontend/app/Explore/page.js`
- Modify: `frontend/components/explore/ProductFamilyRankingsClient.jsx`
- Create: `frontend/components/explore/RankingsSubLens.contract.test.mjs`

**Interfaces:**
- Consumes: `payload.eraSetStrengthV1` (Task 4).
- Produces:
  - `ProductFamilyRankingsClient` accepts a new prop `eraSetStrength = null`.
  - Exported for tests: `nextLensAfterEraDrilldown(eraLens: "rankings"|"packMetrics"): "rankings"|"packMetrics"`.
  - Two pieces of state: `eraLens` (default `"packMetrics"`) and `setLens` (default `"rankings"`).
  - Placeholder bodies rendered in this task are replaced by real components in Tasks 8 and 9.

- [ ] **Step 1: Write the failing contract test**

Create `frontend/components/explore/RankingsSubLens.contract.test.mjs`:

```javascript
// Source-string contract for the Rankings sub-lens hierarchy.
//
// WHY SOURCE STRINGS: ProductFamilyRankingsClient is a large "use client"
// component wired to fetch, entitlements and Next routing. Rendering it in a
// unit test would require standing all of that up, and what the spec actually
// fixes is structural — which controls exist, what their defaults are, and that
// no era arithmetic happens in the browser. Those are checkable in the source
// and would survive any rendering-library change.
//
// RipStatisticsPageClient.jsx has mixed CRLF/LF line endings; this file reads
// components that may too, so every source read is normalised to LF before any
// multi-line anchor is matched.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const client = read("./ProductFamilyRankingsClient.jsx");

test("Eras and Sets each expose a Rankings | Pack Metrics sub-lens", () => {
  assert.match(client, /ERA_LENS_OPTIONS/);
  assert.match(client, /SET_LENS_OPTIONS/);
  for (const source of [client]) {
    assert.match(source, /value:\s*"rankings",\s*label:\s*"Rankings"/);
    assert.match(source, /value:\s*"packMetrics",\s*label:\s*"Pack Metrics"/);
  }
});

test("Eras defaults to Pack Metrics and Sets defaults to Rankings", () => {
  // The existing approved experiences. Changing either default silently would
  // move users' current view without them asking.
  assert.match(client, /useState\("packMetrics"\)/);
  assert.match(client, /useState\("rankings"\)/);
  assert.match(client, /ERA_DEFAULT_LENS = "packMetrics"/);
  assert.match(client, /SET_DEFAULT_LENS = "rankings"/);
});

test("the sub-lens control is visually quieter than the top-level navigation", () => {
  // The primary control keeps variant="primary"; the sub-lens must not.
  assert.match(client, /variant="primary"/);
  assert.match(client, /data-rankings-sub-lens/);
  assert.doesNotMatch(
    client.slice(client.indexOf("data-rankings-sub-lens")),
    /variant="primary"/,
  );
});

test("the era drilldown preserves the active analytical lens", () => {
  assert.match(client, /nextLensAfterEraDrilldown/);
});

test("no era score is computed in the browser", () => {
  // Spec §47: Era Set Strength belongs to the backend ranking contract. The
  // frontend formats and sorts published rows only.
  assert.doesNotMatch(client, /\.reduce\([^)]*setRipV1/);
  assert.doesNotMatch(client, /setRipV1[\s\S]{0,120}?\/\s*(length|count)/);
});

test("the era block is read from the server payload, not assembled here", () => {
  const page = read("../../app/Explore/page.js");
  assert.match(page, /eraSetStrengthV1/);
  assert.match(page, /eraSetStrength=\{/);
});
```

Also add, in the same file:

```javascript
test("the era drilldown maps each lens to its own Sets sub-lens", async () => {
  const { nextLensAfterEraDrilldown } = await import("./ProductFamilyRankingsClient.jsx");
  assert.equal(nextLensAfterEraDrilldown("rankings"), "rankings");
  assert.equal(nextLensAfterEraDrilldown("packMetrics"), "packMetrics");
  // An unknown lens falls back to the Sets default rather than throwing.
  assert.equal(nextLensAfterEraDrilldown("nonsense"), "rankings");
});
```

- [ ] **Step 2: Run to verify it fails**

Run from `frontend`: `npx tsx --test components/explore/RankingsSubLens.contract.test.mjs`
Expected: FAIL on every assertion — none of these symbols exist yet.

- [ ] **Step 3: Pass `eraSetStrength` from the server page**

In `frontend/app/Explore/page.js`, change the `ProductFamilyRankingsClient` invocation to add the prop (keep every existing prop exactly as it is):

```jsx
<ProductFamilyRankingsClient targets={leaderboardTargets} productFamilyRankings={payload?.productFamilyRankings} initialOverallProductRankings={initialOverallProductRankings} openingEconomics={openingEconomics} eraSetStrength={payload?.eraSetStrengthV1 ?? null} loadError={rankingsLoadError} />
```

Immediately above that line, add the comment:

```jsx
        {/* Era Set Strength is a BACKEND contract (eraSetStrengthV1), passed
            through untouched. It is deliberately not derived from
            `leaderboardTargets` here: the client projection truncates the
            cohort to the requested limit, so an era mean computed in this file
            would silently describe a subset. */}
```

- [ ] **Step 4: Add the sub-lens state and control**

In `frontend/components/explore/ProductFamilyRankingsClient.jsx`:

1. Above the component, next to the other module constants, add:

```jsx
/**
 * The secondary analytical lens, inside Eras and inside Sets.
 *
 * TWO SYSTEMS, KEPT APART. Rankings answer "how strong is this entity relative
 * to its peers"; Pack Metrics answer "what does opening one loose pack actually
 * look like". They are produced by different engines from different inputs and
 * are never mixed into one overloaded table.
 */
const LENS_RANKINGS = "rankings";
const LENS_PACK_METRICS = "packMetrics";
const LENS_OPTIONS = [
  { value: LENS_RANKINGS, label: "Rankings" },
  { value: LENS_PACK_METRICS, label: "Pack Metrics" },
];
export const ERA_LENS_OPTIONS = LENS_OPTIONS;
export const SET_LENS_OPTIONS = LENS_OPTIONS;

/** Eras open on the EXISTING approved era experience: pooled pack economics. */
const ERA_DEFAULT_LENS = "packMetrics";
/** Sets open on the EXISTING approved set experience: the Set RIP leaderboard. */
const SET_DEFAULT_LENS = "rankings";

const LENS_COPY = {
  eras: {
    rankings: "Relative Era strength based on the canonical Set RIP scores of the Sets in each era.",
    packMetrics: "Pooled one-pack opening economics across the modeled Sets in each era.",
  },
  sets: {
    rankings: "Relative strength based on how each Set's sealed products rank against comparable products across Pokémon.",
    packMetrics: "One-pack opening economics using each Set's current loose booster pack price and canonical simulation.",
  },
};

/**
 * The user's analytical QUESTION survives the drilldown.
 *
 * Someone comparing era pack economics who clicks into an era wants that era's
 * set pack economics — not a leaderboard. Someone comparing era strength wants
 * the set leaderboard. Dumping both into one Sets subview throws away the
 * intent the click carried.
 */
export function nextLensAfterEraDrilldown(eraLens) {
  return eraLens === LENS_PACK_METRICS ? LENS_PACK_METRICS : SET_DEFAULT_LENS;
}
```

2. Add the new prop to the component signature:

```jsx
export default function ProductFamilyRankingsClient({
  targets,
  productFamilyRankings,
  initialOverallProductRankings,
  loadError,
  openingEconomics = null,
  eraSetStrength = null,
  onUnlockProductRip = null,
}) {
```

3. Next to the existing `const [selectedEra, setSelectedEra] = useState(null);`, add:

```jsx
  // The secondary lens per top-level view. Held separately so switching from
  // Eras to Sets and back does not reset the other lens, and so the drilldown
  // can carry one into the other explicitly rather than by shared state.
  const [eraLens, setEraLens] = useState("packMetrics");
  const [setLens, setSetLens] = useState("rankings");
```

4. Immediately after the existing primary `<SegmentedControl ... variant="primary" ... />` block, add the sub-lens control:

```jsx
      {lens === "eras" || lens === "sets" ? (
        <div className="mb-3" data-rankings-sub-lens={lens}>
          <SegmentedControl
            className="inline-block"
            ariaLabel={lens === "eras" ? "Era analytical lens" : "Set analytical lens"}
            value={lens === "eras" ? eraLens : setLens}
            onChange={lens === "eras" ? setEraLens : setSetLens}
            mobileScroll
            options={LENS_OPTIONS}
          />
          <p className="mt-1.5 max-w-2xl text-xs text-[var(--text-secondary)]">
            {LENS_COPY[lens][lens === "eras" ? eraLens : setLens]}
          </p>
        </div>
      ) : null}
```

Note the deliberate absence of `variant="primary"` — the default `pill` variant is the quieter one, which is what keeps the sub-lens from competing with the top-level navigation.

5. Change the Eras branch of the render so it selects a body by lens, and so the drilldown carries the lens. Replace the existing `) : view === "eras" ? (` branch body with:

```jsx
      ) : view === "eras" ? (
        eraLens === "rankings" ? (
          <EraRankings
            eraSetStrength={eraSetStrength}
            onSelectEra={(era) => {
              const nextLens = nextLensAfterEraDrilldown(eraLens);
              selectView("sets");
              setSetLens(nextLens);
              setSelectedEra(era?.eraName || null);
            }}
          />
        ) : (
          <OpeningEconomicsEras
            economics={openingEconomics}
            onSelectEra={(era) => {
              const nextLens = nextLensAfterEraDrilldown(eraLens);
              selectView("sets");
              setSetLens(nextLens);
              setSelectedEra(era?.eraName || null);
            }}
          />
        )
      ) : view === "sets" ? (
```

6. `selectView` currently resets `selectedEra` to `null`. That must stay — but the drilldown above calls `selectView("sets")` **before** `setSelectedEra(...)`, so the filter still lands. Leave `selectView` unchanged. Do **not** add lens resets to `selectView`: switching top-level views must not throw away the sub-lens the user chose.

7. Inside the `view === "sets"` branch, wrap the existing `<ExploreTableClient ... />` so the Pack Metrics lens can take its place. Replace the existing `<ExploreTableClient .../>` line with:

```jsx
          {setLens === "packMetrics" ? (
            <SetPackMetrics targets={targets} loadError={loadError} eraFilter={selectedEra} />
          ) : (
            <ExploreTableClient targets={targets} loadError={loadError} canViewProductRipIntelligence={canViewProductRipIntelligence} onUnlockProductRip={onUnlockProductRip} eraFilter={selectedEra} />
          )}
```

8. Add the two imports at the top of the file:

```jsx
import EraRankings from "./EraRankings";
import SetPackMetrics from "./SetPackMetrics";
```

- [ ] **Step 5: Create minimal placeholder components so the module resolves**

These are replaced wholesale in Tasks 8 and 9. Create `frontend/components/explore/EraRankings.jsx`:

```jsx
"use client";

export default function EraRankings() {
  return null;
}
```

Create `frontend/components/explore/SetPackMetrics.jsx`:

```jsx
"use client";

export default function SetPackMetrics() {
  return null;
}
```

- [ ] **Step 6: Run the contract test**

Run from `frontend`: `npx tsx --test components/explore/RankingsSubLens.contract.test.mjs`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the existing Rankings suites for regressions**

Run from `frontend`: `npx tsx --test components/explore/OpeningEconomics.contract.test.mjs components/explore/ExploreTableClient.contract.test.js components/explore/RankingsCleanup.contract.test.mjs components/explore/SetRipHierarchy.contract.test.mjs`
Expected: all PASS. Paste the real output.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/Explore/page.js frontend/components/explore/ProductFamilyRankingsClient.jsx frontend/components/explore/EraRankings.jsx frontend/components/explore/SetPackMetrics.jsx frontend/components/explore/RankingsSubLens.contract.test.mjs
git commit -m "feat(rankings): Rankings | Pack Metrics sub-lens with lens-preserving era drilldown"
```

---

## Task 8: Era Rankings view

**Files:**
- Create: `frontend/components/explore/eraSetStrengthSelector.mjs`
- Create: `frontend/components/explore/eraSetStrengthSelector.test.mjs`
- Replace: `frontend/components/explore/EraRankings.jsx` (the Task 7 placeholder)

**Interfaces:**
- Consumes: the `eraSetStrengthV1` contract (Task 3/4); `nextLensAfterEraDrilldown` wiring already done in Task 7; `formatPublicRipScore` from `@/constants/exploreRankingConfig`; `money`/`ratioAsPercent` are NOT used here (no money in this view).
- Produces:
  - `eraSetStrengthSelector.mjs` exports: `isEraStrengthAvailable(block)`, `projectEraStrengthRow(era)`, `sortEraStrengthRows(rows, key, direction)`, `ERA_STRENGTH_SORT_OPTIONS`, `DEFAULT_ERA_STRENGTH_SORT`.
  - `EraRankings.jsx` default-exports `EraRankings({ eraSetStrength, onSelectEra })`.

- [ ] **Step 1: Write the failing selector test**

Create `frontend/components/explore/eraSetStrengthSelector.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_ERA_STRENGTH_SORT,
  isEraStrengthAvailable,
  projectEraStrengthRow,
  sortEraStrengthRows,
} from "./eraSetStrengthSelector.mjs";

const era = (overrides = {}) => ({
  eraName: "Mega Evolution",
  eraId: "era-mega",
  score: 78.4,
  publicScore: 7.8,
  rank: 1,
  cohortSize: 2,
  tier: "B",
  eligibleSetCount: 4,
  rankableSetCount: 4,
  coverageComplete: true,
  status: "ranked",
  statusReason: null,
  constituentSets: [
    { setId: "ah", setName: "Ascended Heroes", setRipScore: 88.0, setRipRank: 1, setRipTier: "A" },
    { setId: "me", setName: "Mega Evolution", setRipScore: 74.0, setRipRank: 5, setRipTier: "B" },
    { setId: "px", setName: "Phantasmal Flames", setRipScore: 64.0, setRipRank: 9, setRipTier: "C" },
    { setId: "gg", setName: "Genetic Apex", setRipScore: 87.6, setRipRank: 2, setRipTier: "A" },
  ],
  ...overrides,
});

test("a ranked era projects score, rank, tier and supporting context", () => {
  const row = projectEraStrengthRow(era());

  assert.equal(row.eraName, "Mega Evolution");
  assert.equal(row.score, "7.8 / 10");
  assert.equal(row.rank, "#1 of 2 eras");
  assert.equal(row.tier, "B");
  assert.equal(row.setCount, "4");
  assert.equal(row.available, true);
});

test("Top Set is the strongest constituent by CANONICAL global Set RIP rank", () => {
  // Not an intra-era rank presented as a global one, and not the highest score
  // read independently — the canonical rank is the authority.
  const row = projectEraStrengthRow(era());

  assert.equal(row.topSetName, "Ascended Heroes");
  assert.equal(row.topSetRank, "#1 overall");
});

test("Set Strength Range spans the lowest and highest constituent Set RIP scores", () => {
  const row = projectEraStrengthRow(era());

  assert.equal(row.strengthRange, "6.4 – 8.8");
});

test("an unavailable era carries no score, rank or tier", () => {
  const row = projectEraStrengthRow(
    era({ status: "unavailable", statusReason: "incomplete_set_rip_coverage",
          score: null, publicScore: null, rank: null, tier: null,
          rankableSetCount: 3, coverageComplete: false }),
  );

  assert.equal(row.available, false);
  assert.equal(row.score, null);
  assert.equal(row.rank, null);
  assert.equal(row.tier, null);
  assert.equal(row.coverageNote, "3 of 4 sets modeled");
});

test("cohort size is read from the contract, never assumed to be two", () => {
  const row = projectEraStrengthRow(era({ rank: 3, cohortSize: 7 }));
  assert.equal(row.rank, "#3 of 7 eras");
});

test("availability follows the published block status", () => {
  assert.equal(isEraStrengthAvailable({ status: "available", eras: [era()] }), true);
  assert.equal(isEraStrengthAvailable({ status: "unavailable", eras: [] }), false);
  assert.equal(isEraStrengthAvailable({ status: "available", eras: [] }), false);
  assert.equal(isEraStrengthAvailable(null), false);
});

test("sorting is presentation only and keeps nulls last in both directions", () => {
  const rows = [
    era({ eraName: "Beta", score: 60.0, rank: 2 }),
    era({ eraName: "Alpha", score: 80.0, rank: 1 }),
    era({ eraName: "Gamma", score: null, rank: null, status: "unavailable" }),
  ];

  const desc = sortEraStrengthRows(rows, "score", "desc").map((row) => row.eraName);
  const asc = sortEraStrengthRows(rows, "score", "asc").map((row) => row.eraName);

  assert.deepEqual(desc, ["Alpha", "Beta", "Gamma"]);
  assert.deepEqual(asc, ["Beta", "Alpha", "Gamma"]);
  assert.deepEqual(DEFAULT_ERA_STRENGTH_SORT, { key: "rank", direction: "asc" });
});

test("sorting never rewrites the published rank", () => {
  const rows = [era({ eraName: "Alpha", score: 80.0, rank: 1 }),
                era({ eraName: "Beta", score: 60.0, rank: 2 })];

  const sorted = sortEraStrengthRows(rows, "eraName", "desc");

  assert.deepEqual(sorted.map((row) => row.rank), [2, 1]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run from `frontend`: `npx tsx --test components/explore/eraSetStrengthSelector.test.mjs`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the selector**

Create `frontend/components/explore/eraSetStrengthSelector.mjs`:

```javascript
/**
 * Read-only selectors for the published Era Set Strength V1 contract.
 *
 * WHAT THIS IS
 * ------------
 * Field reads and display formatting for a score the BACKEND has already
 * finalized. Pure: no React, no fetch, and — critically — no aggregation.
 *
 * WHAT THIS DELIBERATELY IS NOT
 * -----------------------------
 * * NOT a calculator. Era Set Strength is the equal-weighted mean of the
 *   canonical Set RIP V1 scores in an era, computed in
 *   `backend/db/services/era_set_strength_service.py`. Nothing in this module
 *   may average `setRipV1.score`, average ranks, or reconstruct an era number
 *   from the targets the page happens to be holding — the page truncates the
 *   cohort to its requested limit, so a client-side mean would silently
 *   describe a subset.
 * * NOT a re-ranking. `rank` and `cohortSize` are published. Sorting this table
 *   changes reading order only.
 * * NOT pack economics. No pack price, EV, entertainment cost or retention
 *   appears here; those belong to the Pack Metrics lens.
 *
 * MISSING VALUES STAY MISSING, matching `openingEconomicsSelector.mjs`.
 */

import { formatPublicRipScore } from "@/constants/exploreRankingConfig";

function finite(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function isEraStrengthAvailable(block) {
  return Boolean(
    block && block.status === "available" && Array.isArray(block.eras) && block.eras.length > 0,
  );
}

/** The strongest constituent by CANONICAL GLOBAL Set RIP rank. */
function topSet(constituents) {
  const ranked = (Array.isArray(constituents) ? constituents : [])
    .filter((row) => finite(row?.setRipRank) !== null)
    .sort((left, right) => finite(left.setRipRank) - finite(right.setRipRank));
  return ranked[0] || null;
}

/** Lowest and highest constituent Set RIP scores, on the public 0-10 scale. */
function strengthRange(constituents) {
  const scores = (Array.isArray(constituents) ? constituents : [])
    .map((row) => finite(row?.setRipScore))
    .filter((score) => score !== null);
  if (scores.length < 2) return null;
  const low = formatPublicRipScore(Math.min(...scores));
  const high = formatPublicRipScore(Math.max(...scores));
  return low === null || high === null ? null : `${low} – ${high}`;
}

/** One era row projected for display. Every cell is a string, number or `null`. */
export function projectEraStrengthRow(era) {
  const available = era?.status === "ranked";
  const publicScore = finite(era?.publicScore);
  const rank = finite(era?.rank);
  const cohortSize = finite(era?.cohortSize);
  const eligible = finite(era?.eligibleSetCount);
  const rankable = finite(era?.rankableSetCount);
  const best = topSet(era?.constituentSets);
  const bestRank = best ? finite(best.setRipRank) : null;
  return {
    eraId: era?.eraId ?? null,
    eraName: String(era?.eraName || ""),
    available,
    score: available && publicScore !== null ? `${publicScore.toFixed(1)} / 10` : null,
    rank: available && rank !== null && cohortSize !== null
      ? `#${rank} of ${cohortSize} ${cohortSize === 1 ? "era" : "eras"}`
      : null,
    tier: available ? (era?.tier ?? null) : null,
    setCount: eligible === null ? null : String(eligible),
    topSetName: best?.setName ?? null,
    topSetRank: bestRank === null ? null : `#${bestRank} overall`,
    strengthRange: available ? strengthRange(era?.constituentSets) : null,
    coverageNote: available || eligible === null || rankable === null
      ? null
      : `${rankable} of ${eligible} sets modeled`,
    statusReason: era?.statusReason ?? null,
  };
}

/** Sortable Era Rankings columns. Presentation order only. */
export const ERA_STRENGTH_SORT_OPTIONS = [
  { value: "rank", label: "Rank" },
  { value: "eraName", label: "Era" },
  { value: "score", label: "Era Set Strength" },
  { value: "eligibleSetCount", label: "Sets" },
];

export const DEFAULT_ERA_STRENGTH_SORT = { key: "rank", direction: "asc" };

function sortValue(era, key) {
  if (key === "eraName") return String(era?.eraName || "");
  return finite(era?.[key]);
}

/**
 * Presentation sort. Nulls stay LAST in BOTH directions — a missing value is
 * not a small value — matching the existing rankings and era-economics sorts.
 * The published `rank` on each row is never rewritten.
 */
export function sortEraStrengthRows(eras, key, direction) {
  const rows = Array.isArray(eras) ? [...eras] : [];
  const factor = direction === "asc" ? 1 : -1;
  return rows.sort((left, right) => {
    const leftValue = sortValue(left, key);
    const rightValue = sortValue(right, key);
    if (typeof leftValue === "string" || typeof rightValue === "string") {
      return String(leftValue).localeCompare(String(rightValue)) * factor;
    }
    if (leftValue === null && rightValue === null) {
      return String(left?.eraName || "").localeCompare(String(right?.eraName || ""));
    }
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    if (leftValue === rightValue) {
      return String(left?.eraName || "").localeCompare(String(right?.eraName || ""));
    }
    return (leftValue - rightValue) * factor;
  });
}
```

- [ ] **Step 4: Run the selector test**

Run from `frontend`: `npx tsx --test components/explore/eraSetStrengthSelector.test.mjs`
Expected: 8 passed.

If `formatPublicRipScore` returns a number rather than a string, the `strengthRange` assertion `"6.4 – 8.8"` will still pass through template interpolation — but confirm the exact shape by running `node -e "..."` against `frontend/constants/exploreRankingConfig.mjs` first, and adjust only the two `formatPublicRipScore` call sites if the helper expects a 0–10 input rather than a 0–100 one. Set RIP scores are 0–100.

- [ ] **Step 5: Replace the EraRankings placeholder**

Replace `frontend/components/explore/EraRankings.jsx` entirely:

```jsx
"use client";

import React, { useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { RipTierMark } from "./RipScoreBadge.jsx";
import styles from "./explore.module.css";
import {
  DEFAULT_ERA_STRENGTH_SORT,
  isEraStrengthAvailable,
  projectEraStrengthRow,
  sortEraStrengthRows,
} from "./eraSetStrengthSelector.mjs";

/**
 * Eras -> Rankings: which era holds the strongest sets.
 *
 * This is NOT the era pack-economics table. An era can have attractive opening
 * economics while its sealed-product ecosystem ranks poorly, and vice versa —
 * so no pack price, EV, entertainment cost or retention column appears here.
 * Every number is published by `eraSetStrengthV1`; nothing is aggregated in the
 * browser.
 */

const COLUMNS = [
  { key: "rank", label: "Rank", sort: "rank", align: "left" },
  { key: "eraName", label: "Era", sort: "eraName", align: "left" },
  { key: "score", label: "Era Set Strength", sort: "score", emphasis: "primary" },
  { key: "tier", label: "Tier", sort: null },
  { key: "setCount", label: "Sets", sort: "eligibleSetCount" },
  { key: "topSet", label: "Top Set", sort: null, align: "left" },
  { key: "strengthRange", label: "Set Strength Range", sort: null, emphasis: "quiet" },
];

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function Unavailable({ note }) {
  return (
    <span className="text-xs text-[var(--text-secondary)]">
      Unavailable{note ? <span className="ml-1 opacity-70">· {note}</span> : null}
    </span>
  );
}

export default function EraRankings({ eraSetStrength, onSelectEra = null }) {
  const [sort, setSort] = useState(DEFAULT_ERA_STRENGTH_SORT);

  const rows = useMemo(() => {
    const eras = Array.isArray(eraSetStrength?.eras) ? eraSetStrength.eras : [];
    return sortEraStrengthRows(eras, sort.key, sort.direction).map((era) => ({
      raw: era,
      cells: projectEraStrengthRow(era),
    }));
  }, [eraSetStrength, sort]);

  if (!isEraStrengthAvailable(eraSetStrength)) {
    return (
      <section className={`${styles.surface} rounded-xl px-4 py-12`} data-era-rankings-empty>
        <p className="text-center text-sm text-[var(--text-secondary)]">
          Era rankings are temporarily unavailable.
        </p>
      </section>
    );
  }

  const toggleSort = (key) => {
    if (!key) return;
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "desc" ? "asc" : "desc" }
        : { key, direction: key === "eraName" || key === "rank" ? "asc" : "desc" },
    );
  };

  const drilldownLabel = (eraName) => `View the ${eraName} set rankings`;

  const EraName = ({ cells }) =>
    onSelectEra ? (
      <button
        type="button"
        onClick={() => onSelectEra({ eraName: cells.eraName })}
        data-era-strength-drilldown
        aria-label={drilldownLabel(cells.eraName)}
        className="text-sm font-medium text-[var(--text-primary)] underline-offset-2 hover:underline"
      >
        {cells.eraName}
      </button>
    ) : (
      <span className="text-sm font-medium text-[var(--text-primary)]">{cells.eraName}</span>
    );

  return (
    <section data-era-rankings>
      <header className="mb-4">
        <h2 className="text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">
          Era Set Strength
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Which era holds the strongest sets, by the canonical Set RIP score of every set in it.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
          <span>Equal set weighting</span>
          <InfoPopover text="Era Set Strength is the average canonical Set RIP score of the sets in an era, with every set weighted equally. It is not an opening-economics statistic: an era can rank strongly here while its packs return poorly, and the reverse. Tier reflects score strength; rank reflects placement among eras. An era is ranked only when every one of its eligible sets carries a Set RIP result and it has at least three of them." />
        </div>
      </header>

      {/* Desktop */}
      <div className={`${styles.surface} hidden overflow-x-auto rounded-xl px-1 py-1 desk:block`}>
        <table className="w-full text-sm" data-era-strength-table>
          <caption className="sr-only">
            Era Set Strength. Sortable; sorting changes display order only and never changes a
            published era rank.
          </caption>
          <thead>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort.key === column.sort;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    className={`text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)] ${
                      column.align === "left" ? "text-left" : "text-right"
                    }`}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  >
                    {column.sort ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.sort)}
                        data-era-strength-sort={column.sort}
                        className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-[var(--text-primary)]"
                      >
                        {column.label}
                        <span aria-hidden="true" className={active ? "opacity-100" : "opacity-0"}>
                          {sort.direction === "asc" ? "↑" : "↓"}
                        </span>
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ cells }) => (
              <tr key={cells.eraName} data-era-strength-row={cells.eraName}>
                <td className="text-left text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  {cells.available && cells.rank ? cells.rank.split(" ")[0] : <Dash />}
                </td>
                <th scope="row" className="text-left">
                  <EraName cells={cells} />
                </th>
                <td className="text-right tabular-nums">
                  {cells.available ? (
                    <>
                      <span className="text-sm font-semibold text-[var(--text-primary)]">{cells.score}</span>
                      <span className="ml-2 text-[0.65rem] text-[var(--text-secondary)]">{cells.rank}</span>
                    </>
                  ) : (
                    <Unavailable note={cells.coverageNote} />
                  )}
                </td>
                <td className="text-center">
                  {cells.tier ? <RipTierMark tier={cells.tier} /> : <Dash />}
                </td>
                <td className="text-right text-xs tabular-nums text-[var(--text-primary)]">
                  {cells.setCount ?? <Dash />}
                </td>
                <td className="text-left">
                  {cells.topSetName ? (
                    <span className="text-xs text-[var(--text-primary)]">
                      {cells.topSetName}
                      {cells.topSetRank ? (
                        <span className="ml-1.5 text-[0.65rem] text-[var(--text-secondary)]">
                          {cells.topSetRank}
                        </span>
                      ) : null}
                    </span>
                  ) : (
                    <Dash />
                  )}
                </td>
                <td className="text-right text-xs tabular-nums text-[var(--text-secondary)]">
                  {cells.strengthRange ?? <Dash />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: one card per era. */}
      <ul className="space-y-2.5 desk:hidden" data-era-strength-cards>
        {rows.map(({ cells }) => (
          <li key={cells.eraName} className={`${styles.surface} rounded-xl p-3.5`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="flex items-baseline gap-2">
                <b className="text-sm tabular-nums text-[var(--text-primary)]">
                  {cells.available && cells.rank ? cells.rank.split(" ")[0] : "—"}
                </b>
                <EraName cells={cells} />
              </span>
              {cells.tier ? <RipTierMark tier={cells.tier} /> : null}
            </div>
            {cells.available ? (
              <div className="mt-2.5">
                <div className="text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">
                  Era Set Strength
                </div>
                <div className="mt-0.5 text-base font-semibold tabular-nums text-[var(--text-primary)]">
                  {cells.score}
                </div>
                <div className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">{cells.rank}</div>
              </div>
            ) : (
              <p className="mt-2.5">
                <Unavailable note={cells.coverageNote} />
              </p>
            )}
            <dl className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--ex-line)] pt-2 text-[0.68rem] text-[var(--text-secondary)]">
              <div className="flex gap-1.5">
                <dt>Sets</dt>
                <dd className="tabular-nums text-[var(--text-primary)]">{cells.setCount ?? "—"}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>Top Set</dt>
                <dd className="text-[var(--text-primary)]">
                  {cells.topSetName ?? "—"}
                  {cells.topSetRank ? <span className="ml-1 opacity-70">{cells.topSetRank}</span> : null}
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 6: Run the selector test and the sub-lens contract test**

Run from `frontend`: `npx tsx --test components/explore/eraSetStrengthSelector.test.mjs components/explore/RankingsSubLens.contract.test.mjs`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/components/explore/eraSetStrengthSelector.mjs frontend/components/explore/eraSetStrengthSelector.test.mjs frontend/components/explore/EraRankings.jsx
git commit -m "feat(rankings): Era Set Strength rankings table and mobile cards"
```

---

## Task 9: Set Pack Metrics view

**Files:**
- Create: `frontend/components/explore/setPackMetricsSelector.mjs`
- Create: `frontend/components/explore/setPackMetricsSelector.test.mjs`
- Replace: `frontend/components/explore/SetPackMetrics.jsx` (the Task 7 placeholder)

**Interfaces:**
- Consumes: projected targets (Task 6) carrying `name`, `set_id`/`target_id`, `era`, `pack_cost`, `mean_value`, `median_value`, `prob_profit`, `mean_value_to_cost_ratio`, `median_value_to_cost_ratio`, `expected_loss_when_losing`, `p95_value_to_cost_ratio`, `p99_value_to_cost_ratio`; `money` / `ratioAsPercent` from `openingEconomicsSelector.mjs`; `buildTcgSetHrefFromTarget` from `@/lib/explore/ripStatisticsRouting`.
- Produces:
  - `setPackMetricsSelector.mjs` exports: `readSetPackMetrics(target)`, `projectSetPackMetricsRow(target)`, `sortSetPackMetricsRows(targets, key, direction)`, `SET_PACK_METRICS_SORT_OPTIONS`, `DEFAULT_SET_PACK_METRICS_SORT`.
  - `SetPackMetrics.jsx` default-exports `SetPackMetrics({ targets, loadError, eraFilter })`.

**Scope note to state when reporting this task:** spec §33 lists P05, Coefficient of Variation and jackpot concentration as candidate disclosure metrics, but they do **not** exist canonically on the Rankings target (only P95/P99 *value-to-cost ratios* and `expected_loss_when_losing` do). §33 also says "only expose values that already exist canonically. Do not invent new metrics during this UI pass." The disclosure therefore ships P95 ratio, P99 ratio and Average Loss When Losing, and P05 / CoV / jackpot are explicitly out of scope pending a backend field.

- [ ] **Step 1: Write the failing selector test**

Create `frontend/components/explore/setPackMetricsSelector.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_SET_PACK_METRICS_SORT,
  projectSetPackMetricsRow,
  readSetPackMetrics,
  sortSetPackMetricsRows,
} from "./setPackMetricsSelector.mjs";

const target = (overrides = {}) => ({
  set_id: "sv3pt5",
  target_id: "sv3pt5",
  name: "151",
  era: "Scarlet & Violet",
  pack_cost: 4.0,
  mean_value: 3.0,
  median_value: 1.84,
  prob_profit: 0.21,
  mean_value_to_cost_ratio: 0.75,
  median_value_to_cost_ratio: 0.46,
  expected_loss_when_losing: 2.6,
  p95_value_to_cost_ratio: 3.2,
  p99_value_to_cost_ratio: 9.4,
  ...overrides,
});

test("Modeled Return is EV / price and Model Break-Even IS the EV", () => {
  const metrics = readSetPackMetrics(target());

  assert.equal(metrics.packPrice, 4.0);
  assert.equal(metrics.modelBreakEven, 3.0);
  assert.equal(metrics.modeledReturn, 0.75);
});

test("Entertainment Cost is price minus EV, and its share is that over price", () => {
  const metrics = readSetPackMetrics(target());

  assert.equal(metrics.entertainmentCost, 1.0);
  assert.equal(metrics.entertainmentCostShare, 0.25);
});

test("Entertainment Cost is NOT Average Loss When Losing", () => {
  // The unconditional price-EV gap says nothing about the size of a loss. A set
  // that returns $0 half the time and 2x the rest has a $0 gap and a full-pack
  // average loss. Conflating them would be a real analytical error.
  const metrics = readSetPackMetrics(target());

  assert.equal(metrics.entertainmentCost, 1.0);
  assert.equal(metrics.averageLossWhenLosing, 2.6);
  assert.notEqual(metrics.entertainmentCost, metrics.averageLossWhenLosing);
});

test("negative Entertainment Cost is legitimate and is never clamped", () => {
  const metrics = readSetPackMetrics(target({ pack_cost: 4.0, mean_value: 5.5 }));

  assert.equal(metrics.entertainmentCost, -1.5);
  assert.equal(metrics.entertainmentCostShare, -0.375);
  assert.equal(projectSetPackMetricsRow(target({ pack_cost: 4.0, mean_value: 5.5 })).entertainmentCost, "-$1.50");
});

test("Typical Retention is P50 / price and is not Modeled Return", () => {
  const metrics = readSetPackMetrics(target());

  assert.equal(metrics.typicalOpening, 1.84);
  assert.equal(metrics.typicalRetention, 0.46);
  assert.notEqual(metrics.typicalRetention, metrics.modeledReturn);
});

test("Modeled Return falls back to EV / price only when the ratio is absent", () => {
  const metrics = readSetPackMetrics(
    target({ mean_value_to_cost_ratio: undefined, mean_value: 3.0, pack_cost: 4.0 }),
  );

  assert.equal(metrics.modeledReturn, 0.75);
});

test("a missing pack price leaves every price-relative metric unavailable", () => {
  const metrics = readSetPackMetrics(
    target({ pack_cost: null, mean_value_to_cost_ratio: null, median_value_to_cost_ratio: null }),
  );

  assert.equal(metrics.packPrice, null);
  assert.equal(metrics.entertainmentCost, null);
  assert.equal(metrics.entertainmentCostShare, null);
  assert.equal(metrics.modeledReturn, null);
  assert.equal(metrics.typicalRetention, null);
});

test("the projected row formats every cell and leaves missing cells null", () => {
  const row = projectSetPackMetricsRow(target());

  assert.equal(row.setName, "151");
  assert.equal(row.packPrice, "$4.00");
  assert.equal(row.modelBreakEven, "$3.00");
  assert.equal(row.typicalOpening, "$1.84");
  assert.equal(row.modeledReturn, "75.0%");
  assert.equal(row.entertainmentCost, "$1.00");
  assert.equal(row.entertainmentCostShare, "25.0%");
  assert.equal(row.typicalRetention, "46.0%");
  assert.equal(row.chanceToRecoverCost, "21.0%");
  assert.equal(projectSetPackMetricsRow(target({ median_value: null })).typicalOpening, null);
});

test("prob_profit published as a percentage is normalised to one scale", () => {
  assert.equal(readSetPackMetrics(target({ prob_profit: 21 })).chanceToRecoverCost, 0.21);
  assert.equal(readSetPackMetrics(target({ prob_profit: 0.21 })).chanceToRecoverCost, 0.21);
});

test("sorting keeps nulls last in both directions and defaults to set name", () => {
  const rows = [
    target({ set_id: "b", name: "Beta", mean_value_to_cost_ratio: 0.6 }),
    target({ set_id: "a", name: "Alpha", mean_value_to_cost_ratio: 0.9 }),
    target({ set_id: "c", name: "Gamma", mean_value_to_cost_ratio: null, mean_value: null }),
  ];

  const desc = sortSetPackMetricsRows(rows, "modeledReturn", "desc").map((row) => row.name);
  const asc = sortSetPackMetricsRows(rows, "modeledReturn", "asc").map((row) => row.name);

  assert.deepEqual(desc, ["Alpha", "Beta", "Gamma"]);
  assert.deepEqual(asc, ["Beta", "Alpha", "Gamma"]);
  assert.deepEqual(DEFAULT_SET_PACK_METRICS_SORT, { key: "setName", direction: "asc" });
});
```

- [ ] **Step 2: Run to verify it fails**

Run from `frontend`: `npx tsx --test components/explore/setPackMetricsSelector.test.mjs`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the selector**

Create `frontend/components/explore/setPackMetricsSelector.mjs`:

```javascript
/**
 * Read-only selectors for ONE SET's canonical loose-booster-pack economics.
 *
 * WHAT THIS IS
 * ------------
 * Reads of the canonical set target's own one-pack simulation — the same
 * calculation run the Set RIP target represents — plus display formatting.
 *
 * WHAT THIS DELIBERATELY IS NOT
 * -----------------------------
 * * NOT the pooled Era or Global distribution. Each set has its OWN P50; using
 *   the pooled median here would print the same "typical opening" on every row.
 * * NOT a ranking. No score, rank or tier is assigned to a set here — Sets ->
 *   Rankings owns that, and this lens never re-ranks a filtered subset.
 * * NOT a cross-format sealed-product read. This is specifically the set's one
 *   loose booster pack.
 *
 * THE THREE RATIOS ARE NOT INTERCHANGEABLE
 * ----------------------------------------
 *   Modeled Return   = EV / price      long-run average return on spend
 *   Typical Retention= P50 / price     what a typical single opening returns
 *   Entertainment Cost = price - EV    what the experience costs on average
 * A right-skewed set can show a healthy Modeled Return and a poor Typical
 * Retention at the same time. Blurring them would misdescribe exactly the sets
 * this view exists to expose.
 *
 * MODEL BREAK-EVEN IS THE EV. It is the same number expressed as a price, never
 * a second independent statistic.
 *
 * MISSING VALUES STAY MISSING, matching `openingEconomicsSelector.mjs`.
 */

import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";

function finite(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * `prob_profit` is published as a probability, but a 0-100 percentage appears
 * on older rows. This is the SAME normalisation `rankingsSort.mjs` applies, so
 * what is compared is what is printed.
 */
function normalizeProbability(value) {
  const parsed = finite(value);
  if (parsed === null) return null;
  return parsed > 1 ? parsed / 100 : parsed;
}

function ratio(numerator, denominator) {
  if (numerator === null || denominator === null || denominator <= 0) return null;
  return numerator / denominator;
}

/** Every canonical one-pack metric for a set, as raw numbers or `null`. */
export function readSetPackMetrics(target) {
  const packPrice = finite(target?.pack_cost);
  // Model Break-Even IS the modeled Expected Value, expressed as a price. The
  // published alias is preferred; `mean_value` is the same number.
  const modelBreakEven =
    finite(target?.modelBreakEvenPrice) ??
    finite(target?.model_break_even_price) ??
    finite(target?.mean_value);
  const typicalOpening = finite(target?.median_value) ?? finite(target?.medianValue);
  const entertainmentCost =
    packPrice === null || modelBreakEven === null ? null : packPrice - modelBreakEven;
  return {
    setId: String(target?.set_id || target?.target_id || ""),
    setName: String(target?.name || ""),
    era: target?.era ?? null,
    packPrice,
    modelBreakEven,
    typicalOpening,
    // Published ratio preferred; the identical ratio from the SAME row's fields
    // otherwise. Never averaged, never taken from a pooled scope.
    modeledReturn: finite(target?.mean_value_to_cost_ratio) ?? ratio(modelBreakEven, packPrice),
    typicalRetention: finite(target?.median_value_to_cost_ratio) ?? ratio(typicalOpening, packPrice),
    // NOT clamped. A set whose EV exceeds its pack cost has a legitimately
    // negative entertainment cost, and hiding that would misreport it.
    entertainmentCost,
    entertainmentCostShare: ratio(entertainmentCost, packPrice),
    chanceToRecoverCost: normalizeProbability(target?.prob_profit),
    // Secondary disclosure. Every one already exists canonically on the target;
    // no new metric is invented here.
    averageLossWhenLosing:
      finite(target?.expected_loss_when_losing) ?? finite(target?.expectedLossWhenLosing),
    p95ValueToCostRatio: finite(target?.p95_value_to_cost_ratio),
    p99ValueToCostRatio: finite(target?.p99_value_to_cost_ratio),
  };
}

/** One row projected for display. Every cell is a string or `null`. */
export function projectSetPackMetricsRow(target) {
  const metrics = readSetPackMetrics(target);
  return {
    setId: metrics.setId,
    setName: metrics.setName,
    era: metrics.era,
    packPrice: money(metrics.packPrice),
    modelBreakEven: money(metrics.modelBreakEven),
    typicalOpening: money(metrics.typicalOpening),
    modeledReturn: ratioAsPercent(metrics.modeledReturn),
    entertainmentCost: money(metrics.entertainmentCost),
    entertainmentCostShare: ratioAsPercent(metrics.entertainmentCostShare),
    typicalRetention: ratioAsPercent(metrics.typicalRetention),
    chanceToRecoverCost: ratioAsPercent(metrics.chanceToRecoverCost),
    averageLossWhenLosing: money(metrics.averageLossWhenLosing),
    p95ValueToCost: ratioAsPercent(metrics.p95ValueToCostRatio),
    p99ValueToCost: ratioAsPercent(metrics.p99ValueToCostRatio),
  };
}

/** Sortable columns. Presentation only — no canonical Set rank is ever rewritten. */
export const SET_PACK_METRICS_SORT_OPTIONS = [
  { value: "setName", label: "Set" },
  { value: "packPrice", label: "Pack Price" },
  { value: "modelBreakEven", label: "Model Break-Even" },
  { value: "typicalOpening", label: "Typical Opening" },
  { value: "modeledReturn", label: "Modeled Return" },
  { value: "entertainmentCost", label: "Entertainment Cost" },
  { value: "entertainmentCostShare", label: "Entertainment Cost %" },
  { value: "typicalRetention", label: "Typical Retention" },
  { value: "chanceToRecoverCost", label: "Chance to Recover Cost" },
];

export const DEFAULT_SET_PACK_METRICS_SORT = { key: "setName", direction: "asc" };

/**
 * Presentation sort. Nulls stay LAST in BOTH directions. This orders the table
 * for reading; it never assigns, derives or re-derives a rank.
 */
export function sortSetPackMetricsRows(targets, key, direction) {
  const rows = Array.isArray(targets) ? [...targets] : [];
  const factor = direction === "asc" ? 1 : -1;
  return rows.sort((left, right) => {
    const leftMetrics = readSetPackMetrics(left);
    const rightMetrics = readSetPackMetrics(right);
    if (key === "setName") {
      return leftMetrics.setName.localeCompare(rightMetrics.setName, "en", { sensitivity: "base" }) * factor;
    }
    const leftValue = leftMetrics[key] ?? null;
    const rightValue = rightMetrics[key] ?? null;
    if (leftValue === null && rightValue === null) {
      return leftMetrics.setName.localeCompare(rightMetrics.setName, "en", { sensitivity: "base" });
    }
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    if (leftValue === rightValue) {
      return leftMetrics.setName.localeCompare(rightMetrics.setName, "en", { sensitivity: "base" });
    }
    return (leftValue - rightValue) * factor;
  });
}
```

- [ ] **Step 4: Run the selector test**

Run from `frontend`: `npx tsx --test components/explore/setPackMetricsSelector.test.mjs`
Expected: 10 passed

- [ ] **Step 5: Replace the SetPackMetrics placeholder**

Replace `frontend/components/explore/SetPackMetrics.jsx` entirely:

```jsx
"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import InfoPopover from "@/components/ui/InfoPopover";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";
import {
  DEFAULT_SET_PACK_METRICS_SORT,
  projectSetPackMetricsRow,
  sortSetPackMetricsRows,
} from "./setPackMetricsSelector.mjs";

/**
 * Sets -> Pack Metrics: what opening one loose booster pack from each set
 * actually looks like.
 *
 * NO SCORE, NO RANK, NO TIER. This lens answers a metric question, not a
 * relative-strength one, and mixing a leaderboard into it would blur exactly
 * the distinction the sub-lens exists to draw. RIP scores stay in Sets ->
 * Rankings, which is one click away.
 *
 * Filtering by era NARROWS the same canonical rows; it never re-ranks them,
 * because there is no rank in this view to re-derive.
 */

const COLUMNS = [
  { key: "setName", label: "Set", sort: "setName", align: "left" },
  { key: "packPrice", label: "Pack Price", sort: "packPrice", emphasis: "quiet" },
  { key: "modelBreakEven", label: "Model Break-Even", sort: "modelBreakEven", emphasis: "quiet" },
  { key: "typicalOpening", label: "Typical Opening", sort: "typicalOpening" },
  { key: "modeledReturn", label: "Modeled Return", sort: "modeledReturn", emphasis: "primary" },
  { key: "entertainmentCost", label: "Entertainment Cost", sort: "entertainmentCost", secondary: "entertainmentCostShare" },
  { key: "typicalRetention", label: "Typical Retention", sort: "typicalRetention" },
  { key: "chanceToRecoverCost", label: "Chance to Recover Cost", sort: "chanceToRecoverCost" },
];

const HELP =
  "Every number is the set's own canonical one-loose-pack simulation at its current pack price. Model Break-Even is the modeled Expected Value expressed as a price — not a second statistic. Modeled Return is EV over price (long-run average); Typical Retention is the median opening over price (what one typical pack returns). Entertainment Cost is price minus Expected Value and is legitimately negative when a set's EV exceeds its pack price.";

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function valueClass(emphasis) {
  if (emphasis === "primary") return "text-sm font-semibold text-[var(--text-primary)]";
  if (emphasis === "quiet") return "text-xs text-[var(--text-secondary)]";
  return "text-xs text-[var(--text-primary)]";
}

function setHref(target) {
  return buildTcgSetHrefFromTarget({
    target_type: "set",
    target_id: target?.set_id || target?.target_id,
    name: target?.name,
  });
}

export default function SetPackMetrics({ targets = [], loadError = false, eraFilter = null }) {
  const [sort, setSort] = useState(DEFAULT_SET_PACK_METRICS_SORT);
  const [expanded, setExpanded] = useState(null);

  const rows = useMemo(() => {
    const era = String(eraFilter || "").trim().toLocaleLowerCase();
    const scoped = era
      ? (targets || []).filter(
          (target) => String(target?.era || "").trim().toLocaleLowerCase() === era,
        )
      : targets || [];
    return sortSetPackMetricsRows(scoped, sort.key, sort.direction).map((target) => ({
      raw: target,
      cells: projectSetPackMetricsRow(target),
    }));
  }, [targets, eraFilter, sort]);

  if (loadError) {
    return (
      <section className={`${styles.surface} rounded-xl px-4 py-12`} data-set-pack-metrics-error>
        <p className="text-center text-sm text-[var(--text-secondary)]">
          Set pack metrics are temporarily unavailable.
        </p>
      </section>
    );
  }

  const toggleSort = (key) => {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "desc" ? "asc" : "desc" }
        : { key, direction: key === "setName" ? "asc" : "desc" },
    );
  };

  return (
    <section data-set-pack-metrics>
      <header className="mb-4">
        <h2 className="text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">
          Pack Metrics by Set
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          What opening one loose booster pack from each set actually looks like, at today&apos;s pack price.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
          <span>{rows.length} {rows.length === 1 ? "set" : "sets"}</span>
          <InfoPopover text={HELP} />
        </div>
      </header>

      {/* Desktop */}
      <div className={`${styles.surface} hidden overflow-x-auto rounded-xl px-1 py-1 desk:block`}>
        <table className="w-full text-sm" data-set-pack-metrics-table>
          <caption className="sr-only">
            One-pack opening economics by set. Sortable; sorting changes display order only and
            assigns no rank.
          </caption>
          <thead>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort.key === column.sort;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    className={`text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)] ${
                      column.align === "left" ? "text-left" : "text-right"
                    }`}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(column.sort)}
                      data-set-pack-metrics-sort={column.sort}
                      className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-[var(--text-primary)]"
                    >
                      {column.label}
                      <span aria-hidden="true" className={active ? "opacity-100" : "opacity-0"}>
                        {sort.direction === "asc" ? "↑" : "↓"}
                      </span>
                    </button>
                  </th>
                );
              })}
              <th scope="col" className="sr-only">Details</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ raw, cells }) => (
              <React.Fragment key={cells.setId || cells.setName}>
                <tr data-set-pack-metrics-row={cells.setId}>
                  <th scope="row" className="text-left">
                    <Link
                      href={setHref(raw)}
                      className="text-sm font-medium text-[var(--text-primary)] underline-offset-2 hover:underline"
                    >
                      {cells.setName}
                    </Link>
                  </th>
                  {COLUMNS.slice(1).map((column) => (
                    <td key={column.key} className="text-right tabular-nums">
                      <span className={valueClass(column.emphasis)}>{cells[column.key] ?? <Dash />}</span>
                      {column.secondary && cells[column.secondary] ? (
                        <span className="ml-1 text-[0.65rem] text-[var(--text-secondary)]">
                          {cells[column.secondary]}
                        </span>
                      ) : null}
                    </td>
                  ))}
                  <td className="text-right">
                    <button
                      type="button"
                      onClick={() => setExpanded((current) => (current === cells.setId ? null : cells.setId))}
                      aria-expanded={expanded === cells.setId}
                      aria-label={`${expanded === cells.setId ? "Hide" : "Show"} advanced pack metrics for ${cells.setName}`}
                      data-set-pack-metrics-disclosure={cells.setId}
                      className="px-2 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    >
                      <span aria-hidden="true">{expanded === cells.setId ? "−" : "+"}</span>
                    </button>
                  </td>
                </tr>
                {expanded === cells.setId ? (
                  <tr data-set-pack-metrics-detail={cells.setId}>
                    <td colSpan={COLUMNS.length + 1} className="px-3 pb-3">
                      {/* Only values that already exist canonically on the set
                          target. P05, coefficient of variation and top-1%
                          concentration are deliberately absent: they are not
                          published on this row, and inventing them in a UI pass
                          would create a statistic with no lineage. */}
                      <dl className="flex flex-wrap gap-x-6 gap-y-1.5 border-t border-[var(--ex-line)] pt-2.5 text-[0.68rem] text-[var(--text-secondary)]">
                        {[
                          ["Average Loss When Losing", cells.averageLossWhenLosing],
                          ["P95 value / pack price", cells.p95ValueToCost],
                          ["P99 value / pack price", cells.p99ValueToCost],
                        ].map(([label, value]) => (
                          <div key={label} className="flex gap-1.5">
                            <dt>{label}</dt>
                            <dd className="tabular-nums text-[var(--text-primary)]">{value ?? "—"}</dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                ) : null}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: primary metrics first, secondary compact row beneath. */}
      <ul className="space-y-2.5 desk:hidden" data-set-pack-metrics-cards>
        {rows.map(({ raw, cells }) => (
          <li key={cells.setId || cells.setName} className={`${styles.surface} rounded-xl p-3.5`}>
            <Link
              href={setHref(raw)}
              className="text-sm font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
            >
              {cells.setName}
            </Link>

            <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2">
              {[
                ["Modeled Return", cells.modeledReturn, true],
                ["Typical Opening", cells.typicalOpening, false],
                ["Entertainment Cost", cells.entertainmentCost, false],
                ["Typical Retention", cells.typicalRetention, false],
              ].map(([label, value, strong]) => (
                <div key={label}>
                  <dt className="text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">{label}</dt>
                  <dd
                    className={`mt-0.5 tabular-nums ${
                      strong
                        ? "text-base font-semibold text-[var(--text-primary)]"
                        : "text-sm text-[var(--text-primary)]"
                    }`}
                  >
                    {value ?? <Dash />}
                  </dd>
                </div>
              ))}
            </dl>

            <dl className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--ex-line)] pt-2 text-[0.68rem] text-[var(--text-secondary)]">
              {[
                ["Pack Price", cells.packPrice],
                ["Break-Even", cells.modelBreakEven],
                ["Recover Cost", cells.chanceToRecoverCost],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-1.5">
                  <dt>{label}</dt>
                  <dd className="tabular-nums text-[var(--text-primary)]">{value ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      {rows.length === 0 ? (
        <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">
          No sets match the current filter.
        </p>
      ) : null}

      <p className="mt-3 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">
        Card values reflect modeled gross market value. Selling fees, shipping, liquidity, grading costs, and other
        transaction costs are not deducted.
      </p>
    </section>
  );
}
```

- [ ] **Step 6: Run the tests**

Run from `frontend`: `npx tsx --test components/explore/setPackMetricsSelector.test.mjs components/explore/RankingsSubLens.contract.test.mjs`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/components/explore/setPackMetricsSelector.mjs frontend/components/explore/setPackMetricsSelector.test.mjs frontend/components/explore/SetPackMetrics.jsx
git commit -m "feat(rankings): Sets Pack Metrics table, disclosure and mobile cards"
```

---

## Task 10: Frontend contract tests, full suites and visual QA

**Files:**
- Modify: `frontend/components/explore/RankingsSubLens.contract.test.mjs` (append)
- Modify: `frontend/components/explore/ProductFamilyRankingsClient.jsx` only if a test exposes a real gap

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: no new exports. This task closes spec §46 and §48.

- [ ] **Step 1: Write the remaining contract assertions**

Append to `frontend/components/explore/RankingsSubLens.contract.test.mjs`:

```javascript
const eraRankings = read("./EraRankings.jsx");
const setPackMetrics = read("./SetPackMetrics.jsx");
const eraSelector = read("./eraSetStrengthSelector.mjs");
const packSelector = read("./setPackMetricsSelector.mjs");

test("Set Pack Metrics reads canonical set target fields, not a pooled scope", () => {
  for (const field of ["pack_cost", "mean_value", "median_value", "prob_profit",
                       "mean_value_to_cost_ratio", "median_value_to_cost_ratio"]) {
    assert.match(packSelector, new RegExp(field));
  }
  // The pooled global/era distribution must never leak into a per-set row.
  assert.doesNotMatch(packSelector, /openingEconomicsServer|economics\?\.global|economics\?\.eras/);
});

test("the Pack Metrics lens carries no rank, score or tier", () => {
  // Spec §36: a set ranked #14 globally must never be shown as #4 of an era.
  // The safest guarantee is that this view has no rank at all to re-derive.
  assert.doesNotMatch(setPackMetrics, /RipScoreBadge|RipTierMark/);
  assert.doesNotMatch(packSelector, /\brank\b/i);
});

test("the Rankings lens carries no pack-economics columns", () => {
  for (const forbidden of ["Pack Price", "Model Break-Even", "Entertainment Cost",
                           "Typical Retention", "Chance to Recover"]) {
    assert.doesNotMatch(eraRankings, new RegExp(forbidden));
  }
});

test("Era Set Strength is never leader-normalized in the browser", () => {
  assert.doesNotMatch(eraSelector, /leaderNormalized|\/\s*leader|10\.0\b/);
});

test("the Era Set Strength label is used and 'Era RIP' never appears", () => {
  assert.match(eraRankings, /Era Set Strength/);
  for (const source of [eraRankings, eraSelector, client]) {
    assert.doesNotMatch(source, /Era RIP/);
  }
});

test("the Chance to Recover Cost label is not renamed to Chance to Profit", () => {
  assert.match(setPackMetrics, /Chance to Recover Cost/);
  assert.doesNotMatch(setPackMetrics, /Chance to Profit/);
});

test("no era aggregation happens client-side in any new module", () => {
  for (const source of [eraRankings, eraSelector]) {
    assert.doesNotMatch(source, /fmean|\.reduce\(/);
  }
});

test("the era chip filter is shared by both Sets sub-lenses", () => {
  // The chip is rendered by ProductFamilyRankingsClient above whichever body is
  // active, so a Pack Metrics drilldown shows the same "Showing sets from ..."
  // affordance a Rankings drilldown does.
  const setsBranch = client.slice(client.indexOf('view === "sets"'));
  assert.match(setsBranch, /data-era-filter-chip/);
  assert.match(setsBranch, /eraFilter=\{selectedEra\}/);
});
```

- [ ] **Step 2: Run the contract test**

Run from `frontend`: `npx tsx --test components/explore/RankingsSubLens.contract.test.mjs`
Expected: PASS. If `test("the era chip filter is shared by both Sets sub-lenses")` fails, move the `data-era-filter-chip` block in `ProductFamilyRankingsClient.jsx` so it renders above **both** `SetPackMetrics` and `ExploreTableClient` (it should already, from Task 7 step 7 — verify rather than assume).

- [ ] **Step 3: Run the full frontend suite**

Run from `frontend`: `npm run test:frontend`
Expected: the suite's pre-existing pass state, plus the new files. Report the real pass/fail counts. If anything that passed before now fails, fix the cause — do not adjust the old test to match new behaviour without establishing that the new behaviour is correct.

- [ ] **Step 4: Run the full backend unit suite for the touched areas**

Run: `python -m pytest backend/tests/unit/db/services -q`
Expected: pre-existing pass state plus the new modules. Report the real output.

- [ ] **Step 5: Visual QA**

Start the app per the project's usual dev command (`npm run dev` in `frontend/`, backend on :8000). **Confirm no `next build` is running against `frontend/.next` at the same time.** Then inspect `/Rankings` and record what you actually see for all ten states:

Desktop (≥1200px):
1. Eras → Pack Metrics (the default) — unchanged from today
2. Eras → Rankings
3. Sets → Rankings (the default) — unchanged from today
4. Sets → Pack Metrics
5. Eras → Rankings, click an era → lands on Sets → **Rankings**, filtered
6. Eras → Pack Metrics, click an era → lands on Sets → **Pack Metrics**, filtered
7. In state 5, confirm a set ranked #14 globally still reads #14

Mobile (~390px):
8. All four lens combinations
9. No horizontal page overflow; wide tables scroll inside their own container
10. The sub-lens control reads visibly quieter than the top-level `Overall | Eras | Sets | Products`

Check for: no giant tables, scores and tiers readable, Pack Metrics staying dense, and ranking vs metric terminology never blurring.

- [ ] **Step 6: Fix only what QA actually surfaces**

If QA finds a defect, fix it and re-run the affected test file. If QA finds nothing, say so plainly rather than inventing polish.

- [ ] **Step 7: Cleanup**

```bash
rm -rf frontend/.next
git status --short
```

Review the `git status --short` output line by line. Remove any scratch QA screenshots or temp files this pass created. Leave `logs/run_simulations.log` and `logs/task_scheduler_debug.log` alone — they were already modified before this work started and are pre-existing user work. Do not use broad destructive git commands.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/explore/RankingsSubLens.contract.test.mjs
git commit -m "test(rankings): contract-pin the Rankings/Pack Metrics lens separation"
```

---

## Definition of Done

A user can move through both dimensions coherently, with no methodology mixing:

**Metrics:** Overall → Era Pack Metrics → Set Pack Metrics → Product economics
**Rankings:** Era Set Strength → Set RIP → Product-family RIP ranks

And it is immediately understandable that **metrics tell you what the opening economics are; rankings tell you how strong that entity is relative to its peers.**

Verified by: 13 backend Era Set Strength tests, 3 backend retention-ratio tests, the payload-attach test, 8 era-selector tests, 10 pack-metrics-selector tests, 16 sub-lens contract assertions, the full frontend and backend suites, and the ten-state visual QA pass.

## Deferred / Out of Scope (state these when reporting)

- **P05 opening, Coefficient of Variation, and jackpot/top-1% concentration** (spec §33) are not published on the Rankings set target. Only P95/P99 *value-to-cost ratios* and `expected_loss_when_losing` exist canonically, so those three ship in the disclosure and the rest wait on a backend field. §33's own rule — "only expose values that already exist canonically; do not invent new metrics during this UI pass" — is what defers them.
- **A compact "RIP Intelligence" summary inside the Pack Metrics view** (spec §34) is deliberately not built. §34 makes it conditional on width ("if width becomes poor, leave RIP scores to the Rankings view"), and the eight-column primary table plus a disclosure column already fills the desktop width. RIP scores stay one sub-lens click away.
- **A within-era set rank** is not introduced. §17 and §36 both require the canonical global rank as the default, and no explicitly-labelled intra-era rank was requested for this pass.

## Already Satisfied — No Task Required (verify, do not rebuild)

- **§22 "Why This Set Ranks"** is already live. `ExploreTableClient.jsx:75` imports `whySetRanks`, `RANKINGS_FAMILY_COLUMNS`, `RankingsFamilyCells` and `FamilySnapshot` from `SetRipFamilyBreakdown.jsx`, which renders the per-family `score / rank / tier` lineage from `setRipV1.familyScores` / `displayFamilyScores`. Both blocks are already in the client projection allowlist. This plan preserves it by leaving `ExploreTableClient.jsx` untouched. During Task 10's visual QA, confirm the disclosure still renders under Sets → Rankings and shows no raw pack metrics (§22's closing rule) — but do not modify it.
- **§19 era drilldown into a filtered Sets view** already existed for the Pack Metrics path (`selectedEra` → `eraFilter`). Task 7 does not build it; it makes it lens-aware.
- **§39 access.** Neither `EraRankings.jsx` nor `SetPackMetrics.jsx` reads `useRankingsAccess` or renders `PremiumMetricLock`, so nothing new is paywalled and the existing product-level gating in `ProductRankingsTable` is untouched.
