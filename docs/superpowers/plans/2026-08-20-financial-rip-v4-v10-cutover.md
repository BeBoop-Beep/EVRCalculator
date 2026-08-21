# Financial RIP V4 / Overall RIP V10 Application Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip the canonical Financial RIP / Overall RIP / public contract selection from V3/V9/V9-contract to V4/V10/V10-contract, and update the two application layers (rankings publisher, sealed-product finalization + its repository) that still hard-code the old identities, so the Aug 20 opening-simulation cohort can be finalized and published under V10/V4 without recomputing anything.

**Architecture:** This is a promotion of already-computed, already-tested models — not new scoring logic. `backend/desirability/weighted_rip.py::compute_overall_rip_v10` already exists and is unit-tested; `explore_rip_statistics_service.py` already attaches `overallRipV10`/`financialRipV4`/`publicRipContractV10` blocks to every target additively, alongside the V9/V3 ones. Three things are missing: (1) the two canonical-selection constants still point at V9/V3, (2) the rankings publisher reads target dict keys named `"overallRipV9"`/`"financialRipV3"`/`"publicRipContractV9"` literally instead of resolving them from the canonical selection, and (3) the sealed-product finalization service calls `compute_overall_rip_v9` directly and the repository's select/enrichment-allowlist don't know about the V10/V4 columns migration 073 added.

**Tech Stack:** Python (backend), Supabase/Postgres (already migrated), pytest.

**Spec:** `docs/research/financial_rip_v4_cutover_plan.md`

## Global Constraints

- Do NOT alter any RIP formula or weight. The 90/10 split, Collector Appeal V5, and every Financial RIP V4 weight are locked.
- Do NOT create environment-variable model selection — promotion is exactly the two constants in `scoring_config.py` plus the one in `financial_rip_v3_config.py`.
- Do NOT delete or rewrite V3/V9 history. Every V3/V9 field, constant, and identity string must remain readable and byte-identical on existing rows.
- Do NOT rerun the Monte Carlo simulator, recompute Financial RIP V4, or touch market prices anywhere in this plan.
- Do NOT introduce an unbounded "all rows where V10 is null" update — the `calculation_run_id` cohort boundary in `sealed_product_results_repository.py` must be preserved exactly.
- Migrations 072 and 073 are already applied in production and already present in source (`backend/db/migrations/072_update_public_rip_rpc_to_v10.sql`, `073_...sql`). Do not reapply, edit, or re-author them.

---

## File Structure

- Modify `backend/desirability/scoring_config.py` — flip `CANONICAL_OVERALL_RIP_VERSION`, `CANONICAL_OVERALL_RIP_WEIGHTS`; repoint `canonical_public_rip_contract_version()`.
- Modify `backend/calculations/evr/financial_rip_v3_config.py` — flip `CANONICAL_FINANCIAL_RIP_VERSION`.
- Modify `backend/scripts/pokemon_explore_rankings_publisher.py` — replace 5 hard-coded V9/V3 target-key reads with V10/V4 ones; fix stale "V8 cohort" error text.
- Modify `backend/db/services/sealed_product_rip_finalization_service.py` — call `compute_overall_rip_v10` with `financial_rip_v4_score`, write both legacy V9 fields and new V10 fields.
- Modify `backend/db/repositories/sealed_product_results_repository.py` — extend `_SELECT_FIELDS` and `ENRICHMENT_FIELDS` with the migration-073 V10/V4 columns.
- Modify `frontend/components/explore/canonicalRipV7.mjs` — repoint the two `publicRipContractV9` reads to `publicRipContractV10` (independent of the backend flip per the cutover doc).
- New/extend tests in `backend/tests/unit/desirability/`, `backend/tests/unit/scripts/`, `backend/tests/unit/db/` per Task list below.

---

### Task 1: Flip the two canonical constants

**Files:**
- Modify: `backend/desirability/scoring_config.py:23-24` (drop the now-owned-elsewhere import), `:426-428`, `:502-513` (`canonical_public_rip_contract_version`)
- Modify: `backend/calculations/evr/financial_rip_v3_config.py:365-368` (remove local definition, replace with ownership comment — see revised Step 3 below)
- Test: `backend/tests/unit/desirability/test_scoring_config_canonical_selection.py` (new)
- Test: `backend/tests/unit/calculations/test_financial_rip_canonical_ownership.py` (new — dependency-direction regression)
- Modify (test): `backend/tests/unit/desirability/test_overall_rip_v10_and_financial_v4_integration.py:203`, `backend/tests/unit/desirability/test_financial_rip_v3_public_contract.py:117` — these assert the pre-cutover value directly and must be updated in this task (see revised Step 3)

**Interfaces:**
- Consumes: `OVERALL_RIP_V10_VERSION`, `OVERALL_RIP_V10_WEIGHTS`, `FINANCIAL_RIP_V4_VERSION` (already defined, `scoring_config.py:355-373`); `PUBLIC_RIP_CONTRACT_V10_VERSION` (already defined in `backend/desirability/public_rip_contract_v10.py`).
- Produces: `canonical_overall_rip_is_v10()` now returns `True`; `canonical_financial_rip_is_v4()` now returns `True`; `canonical_publication_identity()` (in `public_rip_publication_contract.py`) now emits V10/V4/V10-contract strings with zero code change there, since it reads these constants indirectly.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/desirability/test_scoring_config_canonical_selection.py
from backend.desirability import scoring_config as sc


def test_canonical_financial_rip_is_v4():
    assert sc.CANONICAL_FINANCIAL_RIP_VERSION == sc.FINANCIAL_RIP_V4_VERSION
    assert sc.canonical_financial_rip_is_v4() is True
    assert sc.canonical_financial_rip_is_v3() is False


def test_canonical_overall_rip_is_v10():
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V10_VERSION
    assert sc.CANONICAL_OVERALL_RIP_WEIGHTS == sc.OVERALL_RIP_V10_WEIGHTS
    assert sc.canonical_overall_rip_is_v10() is True
    assert sc.canonical_overall_rip_is_v9() is False


def test_canonical_public_rip_contract_is_v10():
    from backend.desirability.public_rip_contract_v10 import PUBLIC_RIP_CONTRACT_V10_VERSION
    assert sc.canonical_public_rip_contract_version() == PUBLIC_RIP_CONTRACT_V10_VERSION


def test_v3_v9_history_still_computable():
    """The old identifiers must remain valid, non-canonical, registered versions."""
    assert sc.FINANCIAL_RIP_V3_VERSION in sc.KNOWN_FINANCIAL_RIP_VERSIONS
    assert sc.OVERALL_RIP_V9_VERSION in sc.KNOWN_OVERALL_RIP_VERSIONS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/desirability/test_scoring_config_canonical_selection.py -v`
Expected: FAIL on `test_canonical_financial_rip_is_v4` and `test_canonical_overall_rip_is_v10` (constants still resolve V3/V9).

- [ ] **Step 3 (REVISED — see "Ownership correction" below): Flip the constants**

**Ownership correction, discovered during implementation of the original Step 3:**
The plan originally proposed importing `FINANCIAL_RIP_V4_VERSION` into
`financial_rip_v3_config.py` so it could define `CANONICAL_FINANCIAL_RIP_VERSION =
FINANCIAL_RIP_V4_VERSION` locally. This is INVALID: `financial_rip_v4_config.py`
already imports FROM `financial_rip_v3_config.py` (V4 reuses V3's weight tables and
transform objects by design — see `financial_rip_v4_config.py:60-68`). Importing in
the reverse direction creates a circular import, confirmed empirically
(`ImportError: cannot import name 'FINANCIAL_RIP_V3_COMPONENT_INPUTS' from partially
initialized module ... (most likely due to a circular import)`).

The correct fix is an ownership move, not an import trick (no lazy imports,
function-local imports, duplicated version strings, or import-order hacks):
`financial_rip_v3_config.py` should describe Financial RIP V3 only. It must not own
a cross-model canonical switch that now points away from V3. Ownership of
`CANONICAL_FINANCIAL_RIP_VERSION` moves to `backend/desirability/scoring_config.py`,
which already imports both `FINANCIAL_RIP_V3_VERSION` and `FINANCIAL_RIP_V4_VERSION`
at module scope (no cycle there), and which already owns the exact same kind of
switch for `CANONICAL_OVERALL_RIP_VERSION` — see that module's own comment block at
`scoring_config.py:407-425` ("A second definition of a cutover switch is a second
cutover... there is one").

**Importer audit (completed during planning, so the implementer does not need to
repeat it):** every one of the 25 files in this repo that reference
`CANONICAL_FINANCIAL_RIP_VERSION` already imports it from
`backend.desirability.scoring_config`. The ONLY direct importer of the symbol from
`financial_rip_v3_config` is `scoring_config.py` itself, at line 24
(`CANONICAL_FINANCIAL_RIP_VERSION as _CANONICAL_FINANCIAL_RIP_VERSION`). This means
the ownership move is fully localized to two files — no other module needs
repointing, and none of the 25 importers are "historical V3 consumers" needing a
different symbol (`FINANCIAL_RIP_V3_VERSION`) — they are all true canonical-selection
consumers, already reading from the correct module.

In `backend/calculations/evr/financial_rip_v3_config.py:365-368`, remove the local
definition and replace it with a comment pointing at the new owner, matching the
style of the existing Overall RIP comment in this same file (lines ~373-389):

```python
# ---------------------------------------------------------------------------
# Canonical version resolution (the cutover switch) — OWNED ELSEWHERE
# ---------------------------------------------------------------------------
# This module previously also defined `CANONICAL_FINANCIAL_RIP_VERSION`, pinned to
# FINANCIAL_RIP_V3_VERSION. When the V4 cutover needed it to point at Financial RIP
# V4 instead, importing V4's identity here would create a circular import: V4's own
# config module imports FROM this one (V4 reuses V3's weight tables and transforms).
# The switch therefore lives in `backend.desirability.scoring_config`, which already
# imports both identities at module scope with no cycle, and which already owns the
# identical kind of switch for `CANONICAL_OVERALL_RIP_VERSION` (see the comment
# block above this one for why a second definition of a cutover switch is a second
# cutover). This module describes Financial RIP V3 only.
#
#     from backend.desirability.scoring_config import CANONICAL_FINANCIAL_RIP_VERSION
```

(Delete the old `CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V3_VERSION` line
entirely — do not retain it as a deprecated alias; a second apparent authority with
the same name would make the next cutover ambiguous again.)

In `backend/desirability/scoring_config.py:23-24`, remove the import of the
now-deleted symbol:

```python
# was:
# from backend.calculations.evr.financial_rip_v3_config import (
#     CANONICAL_FINANCIAL_RIP_VERSION as _CANONICAL_FINANCIAL_RIP_VERSION,
#     FINANCIAL_RIP_V3_VERSION as FINANCIAL_RIP_V3_VERSION,
#     ...
# )
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_VERSION as FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS as FINANCIAL_RIP_V3_WEIGHTS,
    OVERALL_RIP_V5_VERSION as OVERALL_RIP_V5_VERSION_FROM_CONFIG,
    OVERALL_RIP_V5_WEIGHTS as OVERALL_RIP_V5_WEIGHTS,
    PUBLIC_RIP_CONTRACT_V5_VERSION as PUBLIC_RIP_CONTRACT_V5_VERSION,
)
```

(i.e. drop only the `CANONICAL_FINANCIAL_RIP_VERSION as _CANONICAL_FINANCIAL_RIP_VERSION`
line from this import block; keep every other line unchanged — they are unrelated to
this task.)

In `backend/desirability/scoring_config.py:426-428`:

```python
# was:
# CANONICAL_FINANCIAL_RIP_VERSION = _CANONICAL_FINANCIAL_RIP_VERSION
# CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V9_VERSION
# CANONICAL_OVERALL_RIP_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V9_WEIGHTS)
CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V4_VERSION
CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V10_VERSION
CANONICAL_OVERALL_RIP_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V10_WEIGHTS)
```

`FINANCIAL_RIP_V4_VERSION` is already imported into `scoring_config.py` at module
scope (line 35, from `backend.calculations.evr.financial_rip_v4_config`), so this is
a direct, non-circular reference — no new import needed for this line.

**Dependency-direction regression (new, required by this revision):** add a focused
test proving the import graph is valid and the ownership move held:

```python
# backend/tests/unit/calculations/test_financial_rip_canonical_ownership.py
import ast
from pathlib import Path


def test_v3_v4_and_scoring_config_import_cleanly():
    import backend.calculations.evr.financial_rip_v3_config  # noqa: F401
    import backend.calculations.evr.financial_rip_v4_config  # noqa: F401
    import backend.desirability.scoring_config as scoring_config

    from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION

    assert scoring_config.CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V4_VERSION


def test_financial_rip_v3_config_does_not_import_v4_config():
    """Structural: the V3 config module must not depend on the V4 one — that
    direction is what caused the circular import this test guards against."""
    source = Path("backend/calculations/evr/financial_rip_v3_config.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "financial_rip_v4_config" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "financial_rip_v4_config" not in alias.name


def test_financial_rip_v3_config_no_longer_defines_canonical_switch():
    """Single-owner invariant: only scoring_config may define this symbol."""
    import backend.calculations.evr.financial_rip_v3_config as v3_config
    assert not hasattr(v3_config, "CANONICAL_FINANCIAL_RIP_VERSION")
```

**Existing tests that assert the OLD value (must be updated in this same task, not
deferred to Task 6, since they directly test the exact constant this task changes):**

- `backend/tests/unit/desirability/test_overall_rip_v10_and_financial_v4_integration.py:203`
  — `assert CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V3_VERSION` inside
  `test_v4_and_v10_are_implemented_but_not_canonical`. This test's whole premise
  (promotion has not happened yet) is now false. Rename the test to something like
  `test_v3_and_v9_remain_computable_as_history` and change its body to assert V4/V10
  ARE canonical while V3/V9 remain registered/computable — do not just flip the
  equality and keep the old name, since the name would then contradict the
  assertion.
- `backend/tests/unit/desirability/test_financial_rip_v3_public_contract.py:117`
  — same pattern; read the surrounding test function name and docstring first (it
  is explicitly about the public contract asserting the canonical identity) and
  update both the assertion and any docstring/name that describes "currently V3" to
  describe the new canonical state, following the same reasoning as the item above.

Do not touch any OTHER test file found in the importer audit — the other 23 files
import the symbol correctly already and do not assert its value against a specific
version, so they need no change from this task.

In `backend/desirability/scoring_config.py:502-513` (`canonical_public_rip_contract_version`):

```python
def canonical_public_rip_contract_version() -> str:
    """The canonical public RIP contract version."""
    from backend.desirability.public_rip_contract_v10 import (
        PUBLIC_RIP_CONTRACT_V10_VERSION,
    )

    return PUBLIC_RIP_CONTRACT_V10_VERSION
```

Also update `_audit_overall_rip_weights()` in the same file: it currently checks `CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V7_VERSION` as its only canonical-consistency guard (lines 628-633). Add the equivalent guard for V10 so a future drift between `CANONICAL_OVERALL_RIP_WEIGHTS` and `OVERALL_RIP_V10_WEIGHTS` fails at import time, matching the existing pattern:

```python
    if CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION:
        if CANONICAL_OVERALL_RIP_WEIGHTS != OVERALL_RIP_V10_WEIGHTS:
            raise ValueError(
                "CANONICAL_OVERALL_RIP_WEIGHTS must match OVERALL_RIP_V10_WEIGHTS "
                "while V10 is the canonical Overall RIP."
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/desirability/test_scoring_config_canonical_selection.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/desirability/scoring_config.py backend/calculations/evr/financial_rip_v3_config.py backend/tests/unit/desirability/test_scoring_config_canonical_selection.py
git commit -m "feat(rip): flip canonical selection to Financial RIP V4 / Overall RIP V10"
```

---

### Task 2: Rankings publisher reads V10/V4 target keys

**Files:**
- Modify: `backend/scripts/pokemon_explore_rankings_publisher.py:192,195,250,270,281,366-369,444`
- Test: `backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py` (new)

**Interfaces:**
- Consumes: `canonical_publication_identity()` from `backend.db.services.public_rip_publication_contract` (unchanged signature — already returns V10/V4 strings after Task 1); target dict keys `"overallRipV10"`, `"financialRipV4"`, `"publicRipContractV10"` already attached to every target by `explore_rip_statistics_service.py` (verified present, additive, alongside V9/V3 keys — no producer-side change needed).
- Produces: `publication_contract(row)` returns `(snapshot, rows)` with `snapshot["overall_rip_version"]`/`snapshot["financial_rip_version"]` now populated from V10/V4 metadata, and `rows[i]["overall_rip_score"/"rank"]`/`["financial_rip_score"/"rank"]` sourced from the V10/V4 target blocks.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py
import pytest
from backend.scripts.pokemon_explore_rankings_publisher import (
    _score_contract_problems,
    publication_contract,
    validate_publication_payload,
)


def _v10_contract():
    pillar = lambda: {
        "score": 50.0, "absoluteScore": 50.0, "relativeScore": 50.0,
        "rank": 1, "tier": "A", "rankedSetCount": 22, "cohortFingerprint": "fp",
    }
    return {
        "overallRip": pillar(), "financialRip": {**pillar(), "components": {}},
        "collectorAppeal": {
            **pillar(),
            "components": {
                "rosterDesirability": {
                    "rank": 1, "tier": "A", "rankedSetCount": 22, "relativeScore": 50.0,
                    "modeledPokemon": [{"name": "Pikachu", "desirabilityScore": 90.0}],
                },
                "desirableOutcomeFrequency": {
                    "rank": 1, "tier": "A", "rankedSetCount": 22, "relativeScore": 50.0,
                },
            },
        },
    }


def test_score_contract_problems_reads_v10_contract_key():
    target = {"set_id": "set-1", "publicRipContractV10": _v10_contract()}
    assert _score_contract_problems(target) == []


def test_score_contract_problems_flags_missing_v10_contract():
    problems = _score_contract_problems({"set_id": "set-1"})
    assert problems == ["set-1: publicRipContractV10 is missing"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py -v`
Expected: FAIL — `_score_contract_problems` still reports `publicRipContractV9 is missing`.

- [ ] **Step 3: Replace the hard-coded V9/V3 keys**

`backend/scripts/pokemon_explore_rankings_publisher.py:192`:
```python
    contract = target.get("publicRipContractV10") or {}
```
`:195`:
```python
        return [f"{label}: publicRipContractV10 is missing"]
```
`:250`:
```python
    targets = [target for target in all_targets if _ranked(target, "overallRipV10")]
```
`:270` (fix stale label too — it already read the wrong version name even under V9):
```python
        problems.append(
            f"incomplete Overall RIP V10 cohort expected={ranked_count} actual={len(targets)}"
        )
```
`:281`:
```python
    if any(not _ranked(target, "financialRipV4") for target in targets):
        problems.append("missing Financial RIP V4 rank")
```
`:366-369`:
```python
        "overall_rip_score": (target.get("overallRipV10") or {}).get("score"),
        "overall_rip_rank": (target.get("overallRipV10") or {}).get("rank"),
        "financial_rip_score": (target.get("financialRipV4") or {}).get("score"),
        "financial_rip_rank": (target.get("financialRipV4") or {}).get("rank"),
```
`:444` (inside `validate_publication_payload`):
```python
        if isinstance(target, dict) and (target.get("overallRipV10") or {}).get("rank") is not None
```

Also update the module docstring at the top (lines 5-17) to describe the V10/V4 publish, so the next reader isn't told a stale story the way the V9 docstring was left after the V8 cutover — this is documentation, not logic, but the same file already flags this exact failure mode as the reason it was rewritten last time.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py -v`
Expected: PASS.

- [ ] **Step 5: No V9 fallback regression test**

```python
def test_publisher_has_no_v9_key_fallback():
    import inspect
    from backend.scripts import pokemon_explore_rankings_publisher as mod
    source = inspect.getsource(mod)
    assert '"overallRipV9"' not in source
    assert '"financialRipV3"' not in source
    assert '"publicRipContractV9"' not in source
```

Run: `python -m pytest backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py -v`
Expected: PASS (confirms Step 3 removed every literal, not just the ones covered by Steps 1-2 fixtures).

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/pokemon_explore_rankings_publisher.py backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py
git commit -m "feat(rip): repoint rankings publisher to Overall RIP V10 / Financial RIP V4 keys"
```

---

### Task 3: Repository — read V4/V10 columns, allow V10 enrichment writes

**Files:**
- Modify: `backend/db/repositories/sealed_product_results_repository.py:17-32,61-68`
- Test: `backend/tests/unit/db/test_sealed_product_results_repository_v10.py` (new)

**Interfaces:**
- Consumes: exact migration-073 column names (confirmed): `financial_rip_v4_score`, `financial_rip_v4_status`, `financial_rip_v4_rankable`, `financial_rip_v4_version`, `financial_rip_v4_payload`, `overall_rip_v10_score`, `overall_rip_v10_version`, `overall_rip_v10_rankable`, `overall_rip_v10_payload`.
- Produces: `_SELECT_FIELDS` includes the 9 new columns so `get_sealed_product_results_for_runs`/`get_sealed_product_results_for_run` return them; `ENRICHMENT_FIELDS` grows to 10 entries (6 legacy + 4 new V10 — `financial_rip_v4_*` is written by the Stage-1 simulation path via `_to_row`, not by enrichment, so only the 4 `overall_rip_v10_*` columns are added to the enrichment allowlist, not all 9).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/test_sealed_product_results_repository_v10.py
from backend.db.repositories.sealed_product_results_repository import (
    ENRICHMENT_FIELDS,
    _SELECT_FIELDS,
    update_sealed_product_enrichment,
)


def test_select_fields_include_v4_and_v10_columns():
    for column in (
        "financial_rip_v4_score", "financial_rip_v4_status", "financial_rip_v4_rankable",
        "financial_rip_v4_version", "financial_rip_v4_payload",
        "overall_rip_v10_score", "overall_rip_v10_version",
        "overall_rip_v10_rankable", "overall_rip_v10_payload",
    ):
        assert column in _SELECT_FIELDS


def test_enrichment_fields_accept_v10_columns():
    for column in (
        "overall_rip_v10_score", "overall_rip_v10_version",
        "overall_rip_v10_rankable", "overall_rip_v10_payload",
    ):
        assert column in ENRICHMENT_FIELDS


def test_enrichment_still_fails_closed_on_unknown_key():
    import pytest
    with pytest.raises(ValueError):
        update_sealed_product_enrichment("row-1", {"financial_rip_v4_score": 10.0})
```

Note on the third test: `financial_rip_v4_score` is deliberately NOT added to `ENRICHMENT_FIELDS` — Phase 4/5 of the spec only requires the finalization service to *write* `overall_rip_v10_*`; Financial RIP V4 is written once, by the Stage-1 simulation path, and must never be touched by the batch enrichment update (that would be a second writer for the same column, which the row's docstring at `sealed_product_results_repository.py:53-59` explicitly rules out).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/test_sealed_product_results_repository_v10.py -v`
Expected: FAIL on the first two tests (columns absent).

- [ ] **Step 3: Extend `_SELECT_FIELDS` and `ENRICHMENT_FIELDS`**

`backend/db/repositories/sealed_product_results_repository.py:17-32`:
```python
_SELECT_FIELDS = (
    "id,calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
    "composition_version,composition_id,distribution_model_version,pack_independence_assumption,"
    "random_pack_count,random_pack_expected_value,guaranteed_component_count,"
    "guaranteed_component_market_value,guaranteed_value_share_of_expected_value,"
    "accessory_value_included,"
    "product_market_cost,price_as_of,price_source,simulation_count,"
    "expected_value,median_value,p05_value,p95_value,p99_value,min_value,max_value,"
    "standard_deviation,chance_to_recover_cost,expected_loss_when_losing,"
    "median_loss_when_losing,total_value_to_cost_ratio,"
    "financial_rip_v3_score,financial_rip_v3_status,financial_rip_v3_rankable,"
    "financial_rip_v3_version,financial_rip_v3_payload,"
    "financial_rip_v4_score,financial_rip_v4_status,financial_rip_v4_rankable,"
    "financial_rip_v4_version,financial_rip_v4_payload,"
    "collector_appeal_score,collector_appeal_version,"
    "overall_rip_score,overall_rip_version,overall_rip_rankable,overall_rip_payload,"
    "overall_rip_v10_score,overall_rip_v10_version,overall_rip_v10_rankable,overall_rip_v10_payload,"
    "created_at,updated_at"
)
```

`:61-68`:
```python
ENRICHMENT_FIELDS = (
    "collector_appeal_score",
    "collector_appeal_version",
    "overall_rip_score",
    "overall_rip_version",
    "overall_rip_rankable",
    "overall_rip_payload",
    "overall_rip_v10_score",
    "overall_rip_v10_version",
    "overall_rip_v10_rankable",
    "overall_rip_v10_payload",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/test_sealed_product_results_repository_v10.py -v`
Expected: PASS. (The third test needs a `supabase` client available or mocked — if `update_sealed_product_enrichment` hits a real client before the `ValueError` check, verify by reading the function: the unknown-key check at lines 78-82 runs before any I/O, so this test does not need network/DB mocking.)

- [ ] **Step 5: Commit**

```bash
git add backend/db/repositories/sealed_product_results_repository.py backend/tests/unit/db/test_sealed_product_results_repository_v10.py
git commit -m "feat(rip): repository reads/writes Financial RIP V4 and Overall RIP V10 columns"
```

---

### Task 4: Sealed-product finalization writes V10 alongside V9

**Files:**
- Modify: `backend/db/services/sealed_product_rip_finalization_service.py:52,111-125`
- Test: `backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py` (new)

**Interfaces:**
- Consumes: `compute_overall_rip_v10(financial_rip_v4_score, collector_appeal_v5_score)` from `backend.desirability.weighted_rip` (existing, tested — returns `{"score", "version", "rankable", ...}` matching `compute_overall_rip_v9`'s shape); `row["financial_rip_v4_score"]` (now selected by Task 3); `ENRICHMENT_FIELDS` (now includes the 4 V10 keys, Task 3).
- Produces: `_enrichment_for(row, appeal)` returns 10 keys instead of 6 — the existing 6 legacy V9 keys UNCHANGED, plus 4 new V10 keys. `finalize_sealed_product_rip` behavior is otherwise identical (same cohort resolution, same skip/unavailable semantics) — this task only changes what one row's enrichment payload contains.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py
from backend.db.services.sealed_product_rip_finalization_service import _enrichment_for


def test_enrichment_writes_both_v9_and_v10():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 39.5}
    appeal = {"score": 60.0, "version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"}

    enrichment = _enrichment_for(row, appeal)

    # legacy V9 fields untouched in shape/meaning
    assert "overall_rip_v9" in enrichment["overall_rip_version"] or "overall_rip_v9" in str(enrichment["overall_rip_payload"].get("version", ""))
    # new V10 fields present
    assert "overall_rip_v10" in enrichment["overall_rip_v10_version"]
    assert enrichment["overall_rip_v10_rankable"] is True


def test_v10_arithmetic_is_exactly_90_10():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 40.0}
    appeal = {"score": 50.0, "version": "collector_appeal_v5_..."}

    enrichment = _enrichment_for(row, appeal)

    expected = 0.90 * 40.0 + 0.10 * 50.0
    assert enrichment["overall_rip_v10_score"] == pytest.approx(expected)


def test_v9_and_v10_use_same_collector_appeal_input_never_diverge():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 39.5}
    appeal = {"score": 60.0, "version": "collector_appeal_v5_..."}

    enrichment = _enrichment_for(row, appeal)

    assert enrichment["collector_appeal_score"] == 60.0
    # both blends were fed the SAME appeal_score local variable — verified by
    # construction (one `appeal_score = appeal.get("score")` line feeds both calls)
    assert enrichment["overall_rip_v10_payload"]["score"] is not None
```

Add `import pytest` at the top of the new test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py -v`
Expected: FAIL — `_enrichment_for` returns only 6 keys today, no `overall_rip_v10_*`.

- [ ] **Step 3: Implement the dual-write**

`backend/db/services/sealed_product_rip_finalization_service.py:52`, add alongside the existing import (do not remove it — V9 keeps computing):
```python
from backend.desirability.weighted_rip import compute_overall_rip_v9, compute_overall_rip_v10
```

`:111-125`:
```python
def _enrichment_for(
    row: Mapping[str, Any],
    appeal: Mapping[str, Any],
) -> Dict[str, Any]:
    """The ten enrichment columns for one row. Pure; performs no I/O.

    V9 (Financial RIP V3-backed) and V10 (Financial RIP V4-backed) are computed
    from the SAME Collector Appeal score, read once into `appeal_score`, so the
    appeal input cannot silently diverge between the two models.
    """
    appeal_score = appeal.get("score")
    overall_v9 = compute_overall_rip_v9(row.get("financial_rip_v3_score"), appeal_score)
    overall_v10 = compute_overall_rip_v10(row.get("financial_rip_v4_score"), appeal_score)
    return {
        "collector_appeal_score": appeal_score,
        "collector_appeal_version": appeal.get("version"),
        "overall_rip_score": overall_v9.get("score"),
        "overall_rip_version": overall_v9.get("version"),
        "overall_rip_rankable": bool(overall_v9.get("rankable")),
        "overall_rip_payload": overall_v9,
        "overall_rip_v10_score": overall_v10.get("score"),
        "overall_rip_v10_version": overall_v10.get("version"),
        "overall_rip_v10_rankable": bool(overall_v10.get("rankable")),
        "overall_rip_v10_payload": overall_v10,
    }
```

`compute_overall_rip_v10` already handles a missing `financial_rip_v4_score` (returns `rankable=False`, `score=None`, per its docstring's "NO SUBSTITUTIONS" contract) — no extra guard needed here; a row without a V4 score simply enriches with `overall_rip_v10_rankable=False`, exactly mirroring how V9 already handles a missing V3 score.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/sealed_product_rip_finalization_service.py backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py
git commit -m "feat(rip): sealed-product finalization writes Overall RIP V10 alongside V9"
```

---

### Task 5: Frontend contract repoint

**Files:**
- Modify: `frontend/components/explore/canonicalRipV7.mjs:143,146`
- Test: existing `frontend/components/explore/canonicalRipV10.contract.test.mjs` (verify it already covers this; extend only if it doesn't)

**Interfaces:**
- Consumes: `safeSource.publicRipContractV10` (already emitted by the backend, additively, per the cutover doc — independent of the backend constants flip).
- Produces: `canonicalRipV7.mjs`'s contract reader now sources from the V10 block.

- [ ] **Step 1: Read the existing V10 contract test to confirm expected shape**

Run: `cat frontend/components/explore/canonicalRipV10.contract.test.mjs` (or open it) and confirm whether it already asserts `canonicalRipV7.mjs` reads `publicRipContractV10`. If it does and currently fails, that is this task's failing test — do not write a new one.

- [ ] **Step 2: Run the existing contract test to verify current state**

Run: `node --test frontend/components/explore/canonicalRipV10.contract.test.mjs` (or the project's actual test runner — check `frontend/package.json` `"test"` script first).
Expected: FAIL if the test already targets V10 reading; if it passes already, this task is a no-op — skip to Task 6, but still grep for `publicRipContractV9` in `canonicalRipV7.mjs` to confirm no lingering reference before closing this task.

- [ ] **Step 3: Repoint the two literal reads**

`frontend/components/explore/canonicalRipV7.mjs:143`:
```javascript
const contract = toObject(safeSource.publicRipContractV10);
```
`:146` — read the surrounding 5 lines first (this plan's research pass only isolated the two line hits; confirm whether line 146 is a second independent read or a key-name list entry before editing) and apply the same `V9` → `V10` substring change.

- [ ] **Step 4: Run test to verify it passes**

Run the same command as Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/explore/canonicalRipV7.mjs
git commit -m "feat(rip): frontend canonical RIP reader sources public contract V10"
```

---

### Task 6: Focused test run, then full relevant suites

**Files:** none (verification only)

- [ ] **Step 1: Run every test written in Tasks 1-5**

```bash
python -m pytest backend/tests/unit/desirability/test_scoring_config_canonical_selection.py backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py backend/tests/unit/db/test_sealed_product_results_repository_v10.py backend/tests/unit/db/test_sealed_product_rip_finalization_service_v10.py -v
```
Expected: all PASS.

- [ ] **Step 2: Run the pre-existing V10/V4 suite that predates this plan**

```bash
python -m pytest backend/tests/unit/calculations/test_financial_rip_v4.py backend/tests/unit/calculations/test_financial_rip_v4_research_parity.py backend/tests/unit/calculations/test_sealed_product_financial_rip_v4.py backend/tests/unit/calculations/test_sealed_product_v4_v10_persistence.py backend/tests/unit/desirability/test_overall_rip_v10_and_financial_v4_integration.py backend/tests/unit/desirability/test_v10_v4_ranking_and_publication_contract.py -v
```
Expected: all PASS. These were written against the pre-cutover (V3/V9-canonical) state that also computes V4/V10 non-canonically — re-verify none of them hard-asserted `canonical_overall_rip_is_v9() is True` in a way Task 1 now breaks. If any does, that assertion is testing the OLD cutover state and must be updated to assert the new one (V10 canonical) — this is expected, not a regression.

- [ ] **Step 3: Run the full Market/RIP/publication suites**

```bash
python -m pytest backend/tests/unit/desirability backend/tests/unit/scripts backend/tests/unit/db backend/tests/unit/calculations -v
```
Expected: zero new failures versus the pre-cutover baseline. If a failure references `overall_rip_v9`/`financial_rip_v3` as the expected canonical string, update that test's expectation to V10/V4 (that test was asserting the promotion boundary this plan intentionally moves) — do not weaken the assertion, retarget it.

- [ ] **Step 4: Frontend test run**

```bash
cd frontend && npm test -- explore
```
(confirm actual script name in `frontend/package.json` first)
Expected: zero new failures.

- [ ] **Step 5: Commit any test-expectation updates from Steps 2-3 separately**

```bash
git add -u
git commit -m "test(rip): update pre-cutover V9-canonical assertions to V10-canonical"
```

(Only if Steps 2-3 required changes; if zero changes were needed, skip this commit.)

---

## Scope Expansion — Post-Task-6 Final Review Findings

The final whole-branch review (run after Tasks 1-6 were individually complete and
approved) found that the plan's Task 1 importer audit — which searched only for the
literal symbols `CANONICAL_FINANCIAL_RIP_VERSION`/`CANONICAL_OVERALL_RIP_VERSION` —
missed several READERS elsewhere in the codebase that compare a HARDCODED V3/V9
column name or identity string against those now-flipped constants. These readers
sit entirely outside the plan's original 5 declared files, so none of the 6
task-scoped reviews (each correctly scoped to its own task's diff) could have
caught this. This is a genuine plan defect, not an implementation bug in Tasks 1-6.

**Files newly brought into scope, and why:**

- `backend/db/services/product_family_rankings_service.py` — `_canonical()`
  (lines ~47-54) compares `row.get("financial_rip_v3_version")` /
  `row.get("overall_rip_version")` (hardcoded V3/V9 COLUMN NAMES) against
  `CANONICAL_FINANCIAL_RIP_VERSION`/`CANONICAL_OVERALL_RIP_VERSION` (now V4/V10).
  These can never match again post-flip — this silently empties sealed-product
  family rankings. CRITICAL: in scope because it directly consumes the constants
  Task 1 flipped.
- `backend/db/services/set_rip_service.py` — raises `ValueError` on the version
  mismatch this produces (lines ~66-70), cascading finding #1 into a hard failure
  that would block the Phase 9 dry-run / Phase 11 publish this whole plan exists to
  enable. CRITICAL: in scope as the direct consequence of fixing finding #1 — must
  be re-verified against the fix, not independently changed.
- `backend/desirability/public_rip_contract_v7.py`, `public_rip_contract_v8.py`,
  `public_rip_contract_v9.py` — each sets `canonicalFinancialRipVersion =
  CANONICAL_FINANCIAL_RIP_VERSION` (the live constant) inside a structurally-frozen
  legacy contract, so post-flip a `publicRipContractV9` block now declares
  `financial_rip_v4_...` while its `financialRip` payload still carries Financial
  RIP V3 numbers — a self-contradictory stored identity. IMPORTANT: in scope
  because it's a direct consequence of the same constant these tasks read, and
  Task 6 already established the correct pattern (pin the literal V3 identity) for
  an equivalent case in a migration-061 SQL test — this applies it consistently.
- `backend/scripts/pokemon_snapshot_builders.py` — the set-page verbatim-copy key
  allowlist (~lines 426-469) stops at `overallRipV9`/`publicRipContractV9`; the
  V10/V4/V10-contract keys were never added, so the set page (which already reads
  V10-primary via `canonicalRipV7.mjs`, per Task 5) silently falls back to the now
  self-contradictory V9 block from the previous bullet. IMPORTANT: in scope because
  it's the direct downstream consumer of the previous finding and of Task 2's V10
  publisher output; the runbook's Phase 13 explicitly requires "no V9 fallback
  winning."
- Test-hygiene fixes localized to files Task 2 and Task 6 already touched (no new
  production files): the Task 2 substring-based no-fallback test scoping, and the
  two falsified migration-history comments Task 6's mechanical V9->V10 pass
  introduced in `test_rip_leaderboard_history_contract.py`.

**Explicitly NOT in scope for this fix wave:** any other file, any refactor beyond
what these 6 findings require, any formula/weight change, any change to Collector
Appeal V5 or the 90/10 composition, any migration, any simulation, any production
write.

## Self-Review Notes

- **Spec coverage:** Phases 1-2 → Task 1. Phase 3 → Task 2. Phase 4-5 → Tasks 3-4. Phase 6 → Task 6. Phase 13 (frontend read audit) → Task 5 plus manual verification in Phase 13 below (not code — a live read, done after deploy). Phases 7-12 (live audit, finalizer run, dry-run, publish, post-publication audit) are explicitly RUNTIME operations against production data, not code changes — they are NOT tasks in this plan; they are the deploy/execution runbook that follows this plan's merge, laid out below.
- **No placeholders:** every code step above shows the literal edit, not a description of one.
- **Type/name consistency:** `_enrichment_for` return-dict keys in Task 4 match `ENRICHMENT_FIELDS` in Task 3 exactly (`overall_rip_v10_score/version/rankable/payload`). `compute_overall_rip_v10`'s signature (`financial_rip_v4_score`, `collector_appeal_v5_score`) matches how Task 4 calls it (`row.get("financial_rip_v4_score")`, `appeal_score`).

---

## Post-Merge Runbook (Phases 7-12 of the original spec — NOT part of the code plan, execute only after Tasks 1-6 are merged and deployed)

This section is operational, not a coding task. Each step is READ-ONLY until Phase 11.

1. **Phase 7 — Pre-publication live audit (read-only).** Resolve the 22 Aug 20 `calculation_run_id`s. Verify each has `simulation_count = 1000000`, Financial RIP V4 ready/rankable, Aug 20 price authority, no substitution from older runs. Report `22 / 22 authoritative` or STOP.
2. **Phase 8 — Finalize sealed product V10.** Only after Phase 7 passes:
   ```bash
   python backend/scripts/finalize_sealed_product_rip.py --help
   python backend/scripts/finalize_sealed_product_rip.py --market-date 2026-08-20
   ```
   Resolve actual flags from `--help` first — do not assume `--market-date` is the only required argument. Do not pass `--allow-unverified-cohort` unless the freshness check unexpectedly fails. Afterward, verify every rankable/CA5-available row has all 4 `overall_rip_v10_*` fields populated, and independently recompute `0.90 * financial_rip_v4_score + 0.10 * collector_appeal_score` against `overall_rip_v10_score` for a sample of rows.
3. **Phase 9 — Dry-run publication.**
   ```bash
   python backend/scripts/build_pokemon_explore_rankings_snapshot.py --all --dry-run --market-date 2026-08-20
   ```
   Required: cohort=22, 22 ranked V10 targets, 22 ranked V4 targets, contiguous ranks 1..22, `publicRipContractV10` on all 22, one Aug 20 `calculation_run_id` per set, no V9/V3 identity in publication metadata. Any invariant failing → STOP, do not proceed to Phase 11.
4. **Phase 10 — Publication gate / manual override justification.** The 167-set scrape batch is 164/167 due to 3 unrelated legacy source-ownership defects (Base, EX Trainer Kit 2 Plusle, EX Trainer Kit Latios) outside the 22-set opening-simulation cohort. `--force-publish` is authorized for this ONE Aug 20 publication only, contingent on Phase 7-9 passing. Do not mark the 167-set batch complete or touch its failed jobs.
5. **Phase 11 — Publish.** Only after Phases 7-9 pass:
   ```bash
   python backend/scripts/build_pokemon_explore_rankings_snapshot.py --all --commit --market-date 2026-08-20 --force-publish
   ```
6. **Phase 12 — Post-publication audit (read-only).** Verify the new `pokemon_public_rip_leaderboard_snapshots` row: `publication_status=complete`, `eligible_cohort_count=22`, `overall_rip_version=overall_rip_v10_90_financial_v4_10_collector_appeal_v5`, `financial_rip_version=financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`, contract=`public_rip_contract_v10`. Verify 22 leaderboard rows, ranks 1..22 exactly once, correct `simulation_calculation_run_id` per set, `source_market_date=2026-08-20`. Verify `pokemon_explore_rankings_snapshot_latest` now exposes V10/V4 and the prior V9/V3 snapshot is untouched.
7. **Phase 13 — Frontend read audit (read-only, manual).** Load the Rankings page's actual payload and confirm: Overall RIP resolves V10, Financial RIP resolves V4, Collector Appeal V5, no V9 fallback winning, ranks/tiers match backend V10, 22 sets visible, no mixed-version cohort. No UI redesign.

**Final report format**, produced after the runbook completes:

```
# CLEAN MAIN
# CANONICAL CUTOVER
# PUBLISHER V10/V4 CONTRACT
# SEALED PRODUCT V10 FINALIZATION
# AUG20 22-RUN AUTHORITY
# DRY RUN
# MANUAL OVERRIDE JUSTIFICATION
# V10 PUBLICATION
# SNAPSHOT ID
# 22 HISTORY ROWS
# V9 HISTORY PRESERVATION
# PUBLIC FRONTEND CONTRACT
# TESTS
# DATABASE MUTATIONS
# SIMULATION RUNS
NONE
# FINAL DECISION
V10_V4_PUBLICATION_COMPLETE   (or V10_V4_PUBLICATION_BLOCKED)
```
