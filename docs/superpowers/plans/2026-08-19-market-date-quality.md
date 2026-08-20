# Market Date Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Market surface its own quality authority — READY / INCOMPLETE / DEGRADED / LEGACY_VERIFIED per market date — so Market publication proceeds on 2026-08-19 on its own 22/22 cohort evidence while the unrelated 164/167 full-batch gate stays closed and untouched.

**Architecture:** Three new backend modules plus one new table. `market_run_evidence.py` resolves qualifying exact-date reconciliation runs per set (queue-linked first, explicit-identity fallback second). `market_date_quality.py` composes cohort + run evidence + valuation inputs into a per-date status, persists it, and reads history with bounded pagination. `market_publication_gate.py` is a Market-only CLI gate that rejects `--force-publish` and defers with exit code 3. The existing `publication_gate.py` and the 167-set contract are not modified. Chain-link math is fixed by passing an accepted-date allowlist *into* `build_index_rows` so excluded dates never become observations in the first place.

**Tech Stack:** Python 3.11, Supabase/PostgREST via `supabase-py`, pytest, plpgsql migrations.

**Spec:** `docs/superpowers/specs/2026-08-19-market-date-quality.md`

## Global Constraints

- DO NOT use `--force-publish`; DO NOT weaken the full 167-set publication gate globally; DO NOT alter the three legacy identity-conflict rows (`base`, `exTrainerKit2Plusle`, `exTrainerKitLatios`); DO NOT rerun scrapes; DO NOT run simulations; DO NOT mutate production.
- No task in this plan runs any command against production. Every test uses in-memory fakes. The only production interaction is the read-only verification in Task 11, which the operator runs manually.
- `backend/db/services/publication_gate.py` is **read-only** for this plan. Do not edit it. Market gating is a parallel module.
- Enforcement cutoff is frozen at `MARKET_QUALITY_ENFORCEMENT_START = "2026-08-18"`. Dates strictly before the cutoff are eligible for `LEGACY_VERIFIED`; dates on or after it are never eligible. This yields Aug 17 -> LEGACY_VERIFIED, Aug 18 -> DEGRADED, Aug 19 -> READY, which the spec accepts.
- Qualifying-run predicate, copied verbatim from the spec and matching the existing SQL in `20260819210000_add_successful_run_reconciliation_repair.sql`: exact set; exact `market_date`; `job_name = pokemon_set_scrape`; `source_system = tcgplayer`; `job_type = price_scrape`; `entity_type = set`; `status = success`; `items_succeeded >= 1`; `items_failed = 0`; `sourceCoverageRatio = 1`; `acceptedVariantGroups > 0`; `positiveNmObservationCount >= acceptedVariantGroups`.
- Market cohort eligibility is exactly `resolve_eligible_sets()` in `backend/db/services/pokemon_market_index_service.py` (`supports_opening_simulation is True` AND `is_public_analytics_eligible(row)`), further filtered by `release_date <= market_date`. Do not write a second definition of the cohort.
- PostgREST page size for all new reads: `PAGE_SIZE = 1000`, matching the existing convention in `pokemon_market_index_service.py`.
- Run the backend venv first: `source .venv-1/Scripts/activate` (Git Bash) from the repo root.

## File Structure

**Create:**
- `backend/db/migrations/20260820120000_create_pokemon_market_date_quality.sql` — quality table (also copied to `supabase/migrations/`).
- `backend/db/services/market_run_evidence.py` — Blocker 3. Resolves qualifying runs to set ids.
- `backend/db/services/market_date_quality.py` — status classification, persistence, paginated history (Blockers 2 + 4 statuses).
- `backend/db/services/market_publication_gate.py` — Market-only CLI gate (Blocker 4 `--force-publish` + exit 3).
- `backend/tests/unit/db/services/test_market_run_evidence.py`
- `backend/tests/unit/db/services/test_market_date_quality.py`
- `backend/tests/unit/db/services/test_market_publication_gate.py`
- `backend/tests/unit/scripts/test_market_publication_integration.py` — Blocker 4 entry-point tests.
- `backend/tests/unit/db/services/test_market_index_quality_chain_math.py` — Blocker 1 numeric regression.

**Modify:**
- `backend/db/services/pokemon_market_index_service.py` — accept `accepted_dates` in `build_index_rows` / `build_market_index_history`; add `resolve_latest_accepted_market_date`.
- `backend/scripts/build_pokemon_market_index_history.py` — Market gate + accepted-date filter.
- `backend/scripts/build_pokemon_market_dashboard_snapshots.py:88-96` — add Market gate alongside the existing batch gate.
- `backend/scripts/build_pokemon_explore_set_value_snapshot.py:99-106` — same.

---

### Task 1: Market Date Quality table

**Files:**
- Create: `backend/db/migrations/20260820120000_create_pokemon_market_date_quality.sql`
- Create: `supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql` (byte-identical copy)
- Test: `backend/tests/unit/db/test_market_date_quality_migration.py`

**Interfaces:**
- Consumes: nothing.
- Produces: table `public.pokemon_market_date_quality` with columns `tcg TEXT`, `market_date DATE`, `status TEXT`, `contract_version TEXT`, `cohort_set_count INT`, `qualifying_set_count INT`, `missing_set_ids JSONB`, `cohort_fingerprint TEXT`, `evidence_json JSONB`, `evaluated_at TIMESTAMPTZ`; unique on `(tcg, market_date, contract_version)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/test_market_date_quality_migration.py
from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[3]
             / "db/migrations/20260820120000_create_pokemon_market_date_quality.sql")


def test_migration_defines_quality_table_and_status_domain():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.pokemon_market_date_quality" in sql
    for status in ("READY", "INCOMPLETE", "DEGRADED", "LEGACY_VERIFIED"):
        assert f"'{status}'" in sql
    # Idempotent upsert target used by persist_market_date_quality.
    assert "UNIQUE (tcg, market_date, contract_version)" in sql


def test_migration_is_mirrored_to_supabase():
    mirror = (Path(__file__).resolve().parents[3].parent
              / "supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql")
    assert mirror.read_text(encoding="utf-8") == MIGRATION.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/test_market_date_quality_migration.py -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Write the migration**

Write `backend/db/migrations/20260820120000_create_pokemon_market_date_quality.sql` with exactly this content:

```sql
-- Market Date Quality: the Market surface's own publication authority.
-- Deliberately independent of public.pokemon_scrape_batches (the 167-set
-- cohort). A Market date is judged only on the canonical Market cohort.
BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_date_quality (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tcg TEXT NOT NULL DEFAULT 'pokemon',
    market_date DATE NOT NULL,
    status TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    cohort_set_count INTEGER NOT NULL DEFAULT 0,
    qualifying_set_count INTEGER NOT NULL DEFAULT 0,
    missing_set_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    cohort_fingerprint TEXT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_market_date_quality_status_check
        CHECK (status IN ('READY', 'INCOMPLETE', 'DEGRADED', 'LEGACY_VERIFIED')),
    CONSTRAINT pokemon_market_date_quality_identity
        UNIQUE (tcg, market_date, contract_version)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_market_date_quality_date
    ON public.pokemon_market_date_quality(tcg, market_date DESC);

COMMIT;
```

Then copy it: `cp backend/db/migrations/20260820120000_create_pokemon_market_date_quality.sql supabase/migrations/`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/test_market_date_quality_migration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/20260820120000_create_pokemon_market_date_quality.sql \
        supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql \
        backend/tests/unit/db/test_market_date_quality_migration.py
git commit -m "feat(market): add pokemon_market_date_quality table"
```

---

### Task 2: Qualifying run resolution (Blocker 3)

**Files:**
- Create: `backend/db/services/market_run_evidence.py`
- Test: `backend/tests/unit/db/services/test_market_run_evidence.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `QUALIFYING_JOB_NAME = "pokemon_set_scrape"`, `QUALIFYING_SOURCE_SYSTEM = "tcgplayer"`, `QUALIFYING_JOB_TYPE = "price_scrape"`, `QUALIFYING_ENTITY_TYPE = "set"`
  - `run_metrics_qualify(run: Mapping[str, Any]) -> bool`
  - `resolve_run_set_id(run: Mapping[str, Any], queue_job_set_ids: Mapping[Any, str]) -> str | None`
  - `qualifying_set_ids_for_date(client, market_date: str) -> set[str]`

Authority order is strict: `queue_job_id -> scrape_jobs.set_id` when the run carries a `queue_job_id`; otherwise the run's own explicit `metadata.set_id`. Canonical scraper telemetry emits `metadata.set_filter` (an operator filter list) and `metadata.items_selected`; a single-element `set_filter` with `items_selected == 1` is an explicit exact identity and is accepted **only** by exact match against a supplied cohort canonical-key map. Nothing else — no names, no fuzzy matching, no prefix matching.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/services/test_market_run_evidence.py
import pytest

from backend.db.services.market_run_evidence import (
    resolve_run_set_id,
    run_metrics_qualify,
)


def _run(**overrides):
    base = {
        "job_name": "pokemon_set_scrape",
        "source_system": "tcgplayer",
        "job_type": "price_scrape",
        "entity_type": "set",
        "status": "success",
        "market_date": "2026-08-19",
        "items_succeeded": 1,
        "items_failed": 0,
        "metadata": {
            "sourceCoverageRatio": 1,
            "acceptedVariantGroups": 12,
            "positiveNmObservationCount": 12,
        },
    }
    base.update(overrides)
    return base


def test_canonical_qualifying_run_passes():
    assert run_metrics_qualify(_run()) is True


def test_wrong_job_family_never_qualifies():
    assert run_metrics_qualify(_run(source_system="pokemontcgio")) is False
    assert run_metrics_qualify(_run(job_name="pokemon_set_backfill")) is False
    assert run_metrics_qualify(_run(job_type="catalog_scrape")) is False
    assert run_metrics_qualify(_run(entity_type="card")) is False


def test_non_success_or_failed_items_never_qualify():
    assert run_metrics_qualify(_run(status="partial_failure")) is False
    assert run_metrics_qualify(_run(items_failed=1)) is False
    assert run_metrics_qualify(_run(items_succeeded=0)) is False


def test_partial_coverage_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 0.99,
                       "acceptedVariantGroups": 12,
                       "positiveNmObservationCount": 12})) is False


def test_zero_accepted_variant_groups_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 1,
                       "acceptedVariantGroups": 0,
                       "positiveNmObservationCount": 0})) is False


def test_insufficient_positive_observations_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 1,
                       "acceptedVariantGroups": 12,
                       "positiveNmObservationCount": 11})) is False


@pytest.mark.parametrize("metadata", [
    None, {}, {"sourceCoverageRatio": "not-a-number",
               "acceptedVariantGroups": 1, "positiveNmObservationCount": 1},
    {"acceptedVariantGroups": 1, "positiveNmObservationCount": 1},
    "a string, not a mapping",
])
def test_malformed_or_missing_metrics_never_qualify(metadata):
    assert run_metrics_qualify(_run(metadata=metadata)) is False


def test_queue_linked_run_resolves_through_scrape_jobs():
    run = _run(queue_job_id=41)
    assert resolve_run_set_id(run, {41: "set-alpha"}) == "set-alpha"


def test_queue_linked_run_with_unknown_job_resolves_to_nothing():
    # A queue link that does not resolve is NOT downgraded to the metadata
    # fallback: the link is the authority and it failed.
    run = _run(queue_job_id=999, metadata={**_run()["metadata"], "set_id": "set-alpha"})
    assert resolve_run_set_id(run, {41: "set-alpha"}) is None


def test_null_queue_job_run_resolves_through_explicit_metadata_set_id():
    run = _run(queue_job_id=None,
               metadata={**_run()["metadata"], "set_id": "set-alpha"})
    assert resolve_run_set_id(run, {}) == "set-alpha"


def test_null_queue_job_run_without_explicit_identity_resolves_to_nothing():
    run = _run(queue_job_id=None)
    assert resolve_run_set_id(run, {}) is None


def test_set_identity_is_never_inferred_from_names():
    run = _run(queue_job_id=None,
               metadata={**_run()["metadata"], "set_name": "Base Set"})
    assert resolve_run_set_id(run, {}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_market_run_evidence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db.services.market_run_evidence'`

- [ ] **Step 3: Write the implementation**

```python
# backend/db/services/market_run_evidence.py
"""Qualifying exact-date reconciliation run evidence for the Market surface.

Mirrors the SQL predicate in
``20260819210000_add_successful_run_reconciliation_repair.sql`` so Python and
Postgres agree on what "qualifying" means.

Set identity authority order (Blocker 3):

1. ``queue_job_id`` -> ``scrape_jobs.set_id`` when the run carries a queue link.
   A run WITH a link that does not resolve is rejected outright - it is not
   downgraded to the weaker fallback.
2. otherwise the run's own explicit ``metadata.set_id``.

Identity is never inferred from names or fuzzy matching.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

QUALIFYING_JOB_NAME = "pokemon_set_scrape"
QUALIFYING_SOURCE_SYSTEM = "tcgplayer"
QUALIFYING_JOB_TYPE = "price_scrape"
QUALIFYING_ENTITY_TYPE = "set"
QUALIFYING_STATUS = "success"

PAGE_SIZE = 1000


def _number(value: Any) -> float | None:
    """Strict numeric coercion. Booleans and non-numeric text are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else (
        int(number) if number is not None else None)


def run_metrics_qualify(run: Mapping[str, Any]) -> bool:
    """True when a run row satisfies the full qualifying-run contract."""
    if str(run.get("job_name") or "") != QUALIFYING_JOB_NAME:
        return False
    if str(run.get("source_system") or "") != QUALIFYING_SOURCE_SYSTEM:
        return False
    if str(run.get("job_type") or "") != QUALIFYING_JOB_TYPE:
        return False
    if str(run.get("entity_type") or "") != QUALIFYING_ENTITY_TYPE:
        return False
    if str(run.get("status") or "").strip().lower() != QUALIFYING_STATUS:
        return False

    succeeded = _int(run.get("items_succeeded"))
    failed = _int(run.get("items_failed"))
    if succeeded is None or succeeded < 1:
        return False
    if failed is None or failed != 0:
        return False

    metadata = run.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    coverage = _number(metadata.get("sourceCoverageRatio"))
    accepted = _number(metadata.get("acceptedVariantGroups"))
    positive = _number(metadata.get("positiveNmObservationCount"))
    if coverage is None or accepted is None or positive is None:
        return False
    return coverage == 1.0 and accepted > 0 and positive >= accepted


def resolve_run_set_id(
    run: Mapping[str, Any],
    queue_job_set_ids: Mapping[Any, str],
) -> str | None:
    """Resolve the exact set a run is authoritative for, or None."""
    queue_job_id = run.get("queue_job_id")
    if queue_job_id is not None:
        resolved = queue_job_set_ids.get(queue_job_id)
        return str(resolved) if resolved else None

    metadata = run.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    explicit = metadata.get("set_id")
    if explicit is None:
        return None
    text = str(explicit).strip()
    return text or None


def _paged(query_factory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list(
            (query_factory().range(offset, offset + PAGE_SIZE - 1).execute()).data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _load_runs_for_date(client: Any, market_date: str) -> list[dict[str, Any]]:
    return _paged(lambda: client.table("scrape_job_runs")
                  .select("id,queue_job_id,market_date,job_name,source_system,job_type,"
                          "entity_type,status,items_succeeded,items_failed,metadata")
                  .eq("market_date", market_date)
                  .eq("job_name", QUALIFYING_JOB_NAME)
                  .eq("source_system", QUALIFYING_SOURCE_SYSTEM)
                  .eq("job_type", QUALIFYING_JOB_TYPE)
                  .eq("entity_type", QUALIFYING_ENTITY_TYPE)
                  .eq("status", QUALIFYING_STATUS)
                  .order("id", desc=False))


def _load_queue_job_set_ids(client: Any, job_ids: Sequence[Any]) -> dict[Any, str]:
    if not job_ids:
        return {}
    unique = list(dict.fromkeys(job_ids))
    resolved: dict[Any, str] = {}
    for start in range(0, len(unique), 100):
        chunk = unique[start:start + 100]
        rows = _paged(lambda chunk=chunk: client.table("scrape_jobs")
                      .select("id,set_id").in_("id", chunk).order("id", desc=False))
        for row in rows:
            if row.get("set_id"):
                resolved[row["id"]] = str(row["set_id"])
    return resolved


def qualifying_set_ids_for_date(client: Any, market_date: str) -> set[str]:
    """Set ids with a qualifying exact-date reconciliation run on market_date."""
    day = str(market_date)[:10]
    runs = [row for row in _load_runs_for_date(client, day)
            if str(row.get("market_date") or "")[:10] == day and run_metrics_qualify(row)]
    queue_job_set_ids = _load_queue_job_set_ids(
        client, [row.get("queue_job_id") for row in runs if row.get("queue_job_id") is not None])
    resolved: set[str] = set()
    for row in runs:
        set_id = resolve_run_set_id(row, queue_job_set_ids)
        if set_id:
            resolved.add(set_id)
    return resolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/services/test_market_run_evidence.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Add the wrong-set and wrong-date integration-level tests**

Append to `backend/tests/unit/db/services/test_market_run_evidence.py`:

```python
from backend.db.services.market_run_evidence import qualifying_set_ids_for_date


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, column, value):
        return _Query([row for row in self._rows if row.get(column) == value])

    def in_(self, column, values):
        return _Query([row for row in self._rows if row.get(column) in values])

    def range(self, start, end):
        self._page = (start, end)
        return self

    def execute(self):
        start, end = getattr(self, "_page", (0, len(self._rows)))
        return _Result(self._rows[start:end + 1])


class _Client:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(list(self._tables.get(name, [])))


def test_wrong_date_run_does_not_satisfy_readiness():
    client = _Client({"scrape_job_runs": [_run(queue_job_id=41, market_date="2026-08-18")],
                      "scrape_jobs": [{"id": 41, "set_id": "set-alpha"}]})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == set()


def test_wrong_set_run_credits_only_its_own_set():
    client = _Client({"scrape_job_runs": [_run(queue_job_id=41)],
                      "scrape_jobs": [{"id": 41, "set_id": "set-beta"}]})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == {"set-beta"}


def test_null_queue_link_with_explicit_identity_is_credited():
    run = _run(queue_job_id=None, metadata={"sourceCoverageRatio": 1,
                                            "acceptedVariantGroups": 5,
                                            "positiveNmObservationCount": 5,
                                            "set_id": "set-gamma"})
    client = _Client({"scrape_job_runs": [run], "scrape_jobs": []})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == {"set-gamma"}
```

- [ ] **Step 6: Run the full file**

Run: `python -m pytest backend/tests/unit/db/services/test_market_run_evidence.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/db/services/market_run_evidence.py \
        backend/tests/unit/db/services/test_market_run_evidence.py
git commit -m "feat(market): resolve qualifying run evidence with non-queue-linked fallback"
```

---

### Task 3: Status classification and paginated quality history (Blockers 2 + 4)

**Files:**
- Create: `backend/db/services/market_date_quality.py`
- Test: `backend/tests/unit/db/services/test_market_date_quality.py`

**Interfaces:**
- Consumes: `qualifying_set_ids_for_date` from Task 2; `resolve_eligible_sets` from `pokemon_market_index_service`.
- Produces:
  - `STATUS_READY = "READY"`, `STATUS_INCOMPLETE = "INCOMPLETE"`, `STATUS_DEGRADED = "DEGRADED"`, `STATUS_LEGACY_VERIFIED = "LEGACY_VERIFIED"`
  - `ACCEPTED_STATUSES = frozenset({STATUS_READY, STATUS_LEGACY_VERIFIED})`
  - `MARKET_QUALITY_CONTRACT_VERSION = "pokemon-market-date-quality-v1"`
  - `MARKET_QUALITY_ENFORCEMENT_START = "2026-08-18"`
  - `QUALITY_TABLE = "pokemon_market_date_quality"`, `PAGE_SIZE = 1000`
  - `classify_market_date(*, market_date, cohort_set_ids, qualifying_set_ids, valuation_set_ids, has_later_accepted_date, legacy_allowlist) -> dict`
  - `evaluate_market_date_quality(client, market_date, *, has_later_accepted_date=False) -> dict`
  - `persist_market_date_quality(client, evaluation) -> int`
  - `read_market_date_quality_history(client, *, through_date=None) -> list[dict]`
  - `accepted_market_dates(client, *, through_date=None) -> set[str]`

Classification rule (deterministic, no hidden fallbacks):
- cohort satisfied (every cohort set has a qualifying run AND `standard`+`top10` valuation inputs) -> `READY`.
- not satisfied AND `market_date < MARKET_QUALITY_ENFORCEMENT_START` AND the date is in the explicit `legacy_allowlist` AND valuation inputs are complete -> `LEGACY_VERIFIED`.
- not satisfied AND a later accepted date already exists -> `DEGRADED` (terminal).
- otherwise -> `INCOMPLETE` (current/recoverable).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/services/test_market_date_quality.py
from backend.db.services.market_date_quality import (
    MARKET_QUALITY_ENFORCEMENT_START,
    STATUS_DEGRADED,
    STATUS_INCOMPLETE,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
    classify_market_date,
)

COHORT = {"a", "b", "c"}


def _classify(**overrides):
    kwargs = {
        "market_date": "2026-08-19",
        "cohort_set_ids": COHORT,
        "qualifying_set_ids": set(COHORT),
        "valuation_set_ids": {"standard": set(COHORT), "top10": set(COHORT)},
        "has_later_accepted_date": False,
        "legacy_allowlist": frozenset(),
    }
    kwargs.update(overrides)
    return classify_market_date(**kwargs)


def test_full_cohort_with_valuation_is_ready():
    result = _classify()
    assert result["status"] == STATUS_READY
    assert result["missingSetIds"] == []


def test_missing_qualifying_run_on_current_date_is_incomplete():
    result = _classify(qualifying_set_ids={"a", "b"})
    assert result["status"] == STATUS_INCOMPLETE
    assert result["missingSetIds"] == ["c"]


def test_missing_qualifying_run_with_a_later_accepted_date_is_degraded():
    result = _classify(qualifying_set_ids={"a", "b"}, has_later_accepted_date=True)
    assert result["status"] == STATUS_DEGRADED


def test_missing_valuation_input_blocks_ready():
    result = _classify(valuation_set_ids={"standard": COHORT, "top10": {"a", "b"}})
    assert result["status"] == STATUS_INCOMPLETE


def test_post_enforcement_date_is_never_legacy_verified():
    # Blocker 4 / spec: incomplete telemetry after the cutoff must NOT be
    # laundered into LEGACY_VERIFIED, even if the operator allowlists it.
    result = _classify(market_date="2026-08-19", qualifying_set_ids=set(),
                       legacy_allowlist=frozenset({"2026-08-19"}))
    assert result["status"] != STATUS_LEGACY_VERIFIED


def test_pre_enforcement_allowlisted_date_is_legacy_verified():
    result = _classify(market_date="2026-08-17", qualifying_set_ids=set(),
                       legacy_allowlist=frozenset({"2026-08-17"}))
    assert result["status"] == STATUS_LEGACY_VERIFIED


def test_pre_enforcement_date_not_allowlisted_is_not_legacy_verified():
    result = _classify(market_date="2026-08-17", qualifying_set_ids=set(),
                       has_later_accepted_date=True)
    assert result["status"] == STATUS_DEGRADED


def test_enforcement_cutoff_is_frozen():
    assert MARKET_QUALITY_ENFORCEMENT_START == "2026-08-18"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_market_date_quality.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/db/services/market_date_quality.py
"""Market Date Quality - the Market surface's own publication authority.

Deliberately independent of ``public.pokemon_scrape_batches``. The 167-set
batch gate answers "is the whole scrape cohort complete"; this module answers
"is the canonical Market cohort trustworthy for this date". A Market date is
never held hostage by a failure outside the Market cohort.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.market_run_evidence import qualifying_set_ids_for_date
from backend.db.services.pokemon_market_index_service import resolve_eligible_sets
from backend.domain.pokemon.market_index import deterministic_fingerprint

QUALITY_TABLE = "pokemon_market_date_quality"
SOURCE_TABLE = "pokemon_set_value_daily_history"
PAGE_SIZE = 1000

MARKET_QUALITY_CONTRACT_VERSION = "pokemon-market-date-quality-v1"

# Frozen pre-enforcement cutoff. Dates strictly before this may be granted
# LEGACY_VERIFIED through the explicit allowlist below; dates on or after it
# never can, no matter how incomplete their telemetry is.
MARKET_QUALITY_ENFORCEMENT_START = "2026-08-18"

# Explicit historical verification path. Membership is a reviewed decision,
# never an automatic consequence of missing evidence.
LEGACY_VERIFIED_ALLOWLIST_ENV = "MARKET_QUALITY_LEGACY_ALLOWLIST"
DEFAULT_LEGACY_VERIFIED_ALLOWLIST = frozenset({"2026-08-17"})

STATUS_READY = "READY"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_DEGRADED = "DEGRADED"
STATUS_LEGACY_VERIFIED = "LEGACY_VERIFIED"

# Statuses whose dates may participate in chain-link math and public authority.
ACCEPTED_STATUSES = frozenset({STATUS_READY, STATUS_LEGACY_VERIFIED})

REQUIRED_VALUE_SCOPES = ("standard", "top10")


def resolve_legacy_allowlist(explicit: Iterable[str] | None = None) -> frozenset[str]:
    if explicit is not None:
        return frozenset(str(day)[:10] for day in explicit)
    raw = os.getenv(LEGACY_VERIFIED_ALLOWLIST_ENV)
    if raw is None:
        return DEFAULT_LEGACY_VERIFIED_ALLOWLIST
    return frozenset(part.strip()[:10] for part in raw.split(",") if part.strip())


def classify_market_date(
    *,
    market_date: str,
    cohort_set_ids: Iterable[str],
    qualifying_set_ids: Iterable[str],
    valuation_set_ids: Mapping[str, Iterable[str]],
    has_later_accepted_date: bool,
    legacy_allowlist: Iterable[str],
) -> dict[str, Any]:
    """Classify one market date. Pure - no I/O, fully determined by its inputs."""
    day = str(market_date)[:10]
    cohort = {str(value) for value in cohort_set_ids}
    qualifying = {str(value) for value in qualifying_set_ids}
    allowlist = {str(value)[:10] for value in legacy_allowlist}

    missing_runs = sorted(cohort - qualifying)
    missing_valuation: dict[str, list[str]] = {}
    for scope in REQUIRED_VALUE_SCOPES:
        present = {str(value) for value in (valuation_set_ids.get(scope) or ())}
        absent = sorted(cohort - present)
        if absent:
            missing_valuation[scope] = absent

    cohort_satisfied = bool(cohort) and not missing_runs and not missing_valuation

    if cohort_satisfied:
        status = STATUS_READY
    elif (day < MARKET_QUALITY_ENFORCEMENT_START
          and day in allowlist
          and not missing_valuation
          and bool(cohort)):
        status = STATUS_LEGACY_VERIFIED
    elif has_later_accepted_date:
        status = STATUS_DEGRADED
    else:
        status = STATUS_INCOMPLETE

    return {
        "marketDate": day,
        "status": status,
        "contractVersion": MARKET_QUALITY_CONTRACT_VERSION,
        "cohortSetCount": len(cohort),
        "qualifyingSetCount": len(cohort & qualifying),
        "missingSetIds": missing_runs,
        "cohortFingerprint": deterministic_fingerprint(sorted(cohort)),
        "evidence": {
            "missingQualifyingRunSetIds": missing_runs,
            "missingValuationSetIds": missing_valuation,
            "enforcementStart": MARKET_QUALITY_ENFORCEMENT_START,
            "preEnforcement": day < MARKET_QUALITY_ENFORCEMENT_START,
            "legacyAllowlisted": day in allowlist,
            "hasLaterAcceptedDate": bool(has_later_accepted_date),
        },
    }


def _paged(query_factory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list(
            (query_factory().range(offset, offset + PAGE_SIZE - 1).execute()).data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def cohort_set_ids_for_date(client: Any, market_date: str) -> list[str]:
    """Canonical Market cohort for a date - the SAME eligibility Market/index uses."""
    day = str(market_date)[:10]
    return sorted(
        str(row["id"]) for row in resolve_eligible_sets(client)
        if not row.get("release_date") or str(row["release_date"])[:10] <= day)


def valuation_set_ids_for_date(
    client: Any, market_date: str, set_ids: Sequence[str]
) -> dict[str, set[str]]:
    """Market valuation inputs present for the date, per required value scope."""
    day = str(market_date)[:10]
    present: dict[str, set[str]] = {scope: set() for scope in REQUIRED_VALUE_SCOPES}
    if not set_ids:
        return present
    ids = list(set_ids)
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        rows = _paged(lambda chunk=chunk: client.table(SOURCE_TABLE)
                      .select("set_id,snapshot_date,set_value,priced_card_count,value_scope")
                      .in_("set_id", chunk)
                      .in_("value_scope", list(REQUIRED_VALUE_SCOPES))
                      .eq("snapshot_date", day)
                      .order("set_id", desc=False))
        for row in rows:
            scope = str(row.get("value_scope") or "")
            if scope not in present:
                continue
            try:
                value = float(row.get("set_value") or 0)
                count = int(row.get("priced_card_count") or 0)
            except (TypeError, ValueError):
                continue
            if value > 0 and count > 0:
                present[scope].add(str(row.get("set_id")))
    return present


def evaluate_market_date_quality(
    client: Any,
    market_date: str,
    *,
    has_later_accepted_date: bool = False,
    legacy_allowlist: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Evaluate one market date from live evidence. Read-only."""
    day = str(market_date)[:10]
    cohort = cohort_set_ids_for_date(client, day)
    return classify_market_date(
        market_date=day,
        cohort_set_ids=cohort,
        qualifying_set_ids=qualifying_set_ids_for_date(client, day),
        valuation_set_ids=valuation_set_ids_for_date(client, day, cohort),
        has_later_accepted_date=has_later_accepted_date,
        legacy_allowlist=resolve_legacy_allowlist(legacy_allowlist),
    )


def persist_market_date_quality(client: Any, evaluation: Mapping[str, Any]) -> int:
    """Upsert the durable diagnostic quality row.

    This is quality STATE, not Market artifact publication - the spec allows it
    even when the date is INCOMPLETE or DEGRADED.
    """
    row = {
        "tcg": "pokemon",
        "market_date": evaluation["marketDate"],
        "status": evaluation["status"],
        "contract_version": evaluation["contractVersion"],
        "cohort_set_count": int(evaluation["cohortSetCount"]),
        "qualifying_set_count": int(evaluation["qualifyingSetCount"]),
        "missing_set_ids": list(evaluation["missingSetIds"]),
        "cohort_fingerprint": evaluation["cohortFingerprint"],
        "evidence_json": dict(evaluation["evidence"]),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table(QUALITY_TABLE).upsert(
        [row], on_conflict="tcg,market_date,contract_version").execute()
    return 1


def read_market_date_quality_history(
    client: Any, *, through_date: str | None = None
) -> list[dict[str, Any]]:
    """Read persisted quality history with BOUNDED PAGINATION (Blocker 2).

    PostgREST caps rows per response. An unpaginated read silently truncates
    older dates, which would let a DEGRADED date reappear as unknown-and-
    therefore-accepted. Every page is requested explicitly via .range().
    """
    def query():
        built = (client.table(QUALITY_TABLE).select("*")
                 .eq("tcg", "pokemon")
                 .eq("contract_version", MARKET_QUALITY_CONTRACT_VERSION)
                 .order("market_date", desc=False))
        if through_date:
            built = built.lte("market_date", str(through_date)[:10])
        return built

    return _paged(query)


def accepted_market_dates(
    client: Any, *, through_date: str | None = None
) -> set[str]:
    """Dates whose persisted status permits chain math and public authority."""
    return {
        str(row["market_date"])[:10]
        for row in read_market_date_quality_history(client, through_date=through_date)
        if str(row.get("status") or "") in ACCEPTED_STATUSES
    }


def resolve_latest_accepted_market_date(
    client: Any, *, through_date: str | None = None
) -> str | None:
    """Latest accepted public Market date. A DEGRADED date can never win."""
    accepted = accepted_market_dates(client, through_date=through_date)
    return max(accepted) if accepted else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/services/test_market_date_quality.py -v`
Expected: PASS

- [ ] **Step 5: Add the pagination regression (Blocker 2)**

Append to `backend/tests/unit/db/services/test_market_date_quality.py`:

```python
import inspect

from backend.db.services import market_date_quality as mdq


class _PagingResult:
    def __init__(self, data):
        self.data = data


class _PagingQuery:
    def __init__(self, rows, calls):
        self._rows, self._calls = rows, calls
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        self._calls.append((start, end))
        return self

    def execute(self):
        start, end = self._range
        return _PagingResult(self._rows[start:end + 1])


class _PagingClient:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, _name):
        return _PagingQuery(self.rows, self.calls)


def test_quality_history_read_paginates_beyond_one_page():
    total = mdq.PAGE_SIZE + 250
    rows = [{"market_date": f"2020-01-01", "status": mdq.STATUS_READY, "n": i}
            for i in range(total)]
    client = _PagingClient(rows)

    result = mdq.read_market_date_quality_history(client)

    assert len(result) == total, "an unpaginated read would truncate at PAGE_SIZE"
    assert client.calls[0] == (0, mdq.PAGE_SIZE - 1)
    assert client.calls[1] == (mdq.PAGE_SIZE, 2 * mdq.PAGE_SIZE - 1)
    assert len(client.calls) >= 2


def test_quality_history_read_source_uses_bounded_range():
    source = inspect.getsource(mdq._paged)
    assert ".range(" in source, "quality history reads must request bounded pages"


def test_accepted_dates_exclude_degraded_and_incomplete():
    class _Static(_PagingClient):
        pass

    client = _Static([
        {"market_date": "2026-08-17", "status": mdq.STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
        {"market_date": "2026-08-19", "status": mdq.STATUS_READY},
    ])
    assert mdq.accepted_market_dates(client) == {"2026-08-17", "2026-08-19"}
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-19"
```

- [ ] **Step 6: Run the full file**

Run: `python -m pytest backend/tests/unit/db/services/test_market_date_quality.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/db/services/market_date_quality.py \
        backend/tests/unit/db/services/test_market_date_quality.py
git commit -m "feat(market): classify market date quality with paginated history reads"
```

---

### Task 4: Quality filter precedes chain math (Blocker 1)

**Files:**
- Modify: `backend/db/services/pokemon_market_index_service.py` (`build_index_rows`, `build_market_index_history`)
- Test: `backend/tests/unit/db/services/test_market_index_quality_chain_math.py`

**Interfaces:**
- Consumes: `ACCEPTED_STATUSES`, `accepted_market_dates` from Task 3.
- Produces: `build_index_rows(sets, source_rows, *, through_date=None, accepted_dates=None)` and `build_market_index_history(client, *, through_date=None, accepted_dates=None)`. When `accepted_dates` is not None, a date absent from it is dropped **before** observations are assembled, so it can never enter `build_chain_linked_history`.

The filter goes in the `all_dates` accumulation loop, which currently sits at the top of `build_index_rows`. This is the only correct location: `build_chain_linked_history` derives each day's `dailyReturn` from the immediately preceding observation, so filtering afterwards would leave Aug 19's return computed against Aug 18.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/services/test_market_index_quality_chain_math.py
"""Blocker 1: a DEGRADED date must have ZERO influence on later index levels."""

from backend.db.services.pokemon_market_index_service import build_index_rows

SETS = [
    {"id": "set-a", "canonical_key": "setA", "release_date": "2020-01-01"},
    {"id": "set-b", "canonical_key": "setB", "release_date": "2020-01-01"},
]


def _source(day, set_id, value, scope="standard"):
    return {"set_id": set_id, "snapshot_date": day, "set_value": value,
            "priced_card_count": 10, "total_card_count": 10, "value_scope": scope,
            "source": "test", "updated_at": f"{day}T00:00:00Z"}


def _rows(aug18_value):
    source_rows = []
    for scope in ("standard", "top10"):
        source_rows += [
            _source("2026-08-17", "set-a", 100.0, scope),
            _source("2026-08-17", "set-b", 100.0, scope),
            _source("2026-08-18", "set-a", aug18_value, scope),
            _source("2026-08-18", "set-b", aug18_value, scope),
            _source("2026-08-19", "set-a", 110.0, scope),
            _source("2026-08-19", "set-b", 110.0, scope),
        ]
    return source_rows


def _aug19(rows):
    return next(row for row in rows
                if row["market_date"] == "2026-08-19" and row["index_key"] == "raw")


ACCEPTED = {"2026-08-17", "2026-08-19"}


def test_degraded_date_is_excluded_before_chain_math():
    rows = build_index_rows(SETS, _rows(500.0), accepted_dates=ACCEPTED)
    dates = sorted({row["market_date"] for row in rows})
    assert dates == ["2026-08-17", "2026-08-19"], "Aug 18 must never be an observation"

    aug19 = _aug19(rows)
    assert aug19["previous_market_date"] == "2026-08-17", "Aug 17 -> Aug 19 transition"


def test_changing_the_degraded_date_cannot_move_the_later_index():
    quiet = _aug19(build_index_rows(SETS, _rows(101.0), accepted_dates=ACCEPTED))
    wild = _aug19(build_index_rows(SETS, _rows(9999.0), accepted_dates=ACCEPTED))

    assert quiet["normalized_index_value"] == wild["normalized_index_value"]
    assert quiet["daily_return"] == wild["daily_return"]
    # 100 -> 110 chained off the BASE 100.0, i.e. exactly +10%.
    assert quiet["daily_return"] == 110.0 / 100.0 - 1.0
    assert quiet["normalized_index_value"] == 110.0


def test_without_the_filter_the_degraded_date_would_have_polluted_the_result():
    # Guard the guard: prove the regression above is actually load-bearing.
    unfiltered = _aug19(build_index_rows(SETS, _rows(9999.0)))
    filtered = _aug19(build_index_rows(SETS, _rows(9999.0), accepted_dates=ACCEPTED))
    assert unfiltered["normalized_index_value"] != filtered["normalized_index_value"]
    assert unfiltered["previous_market_date"] == "2026-08-18"


def test_accepted_dates_none_preserves_existing_behaviour():
    rows = build_index_rows(SETS, _rows(105.0))
    assert sorted({row["market_date"] for row in rows}) == [
        "2026-08-17", "2026-08-18", "2026-08-19"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_market_index_quality_chain_math.py -v`
Expected: FAIL with `TypeError: build_index_rows() got an unexpected keyword argument 'accepted_dates'`

- [ ] **Step 3: Apply the change**

In `backend/db/services/pokemon_market_index_service.py`, change the signature and the date-accumulation loop of `build_index_rows`:

```python
def build_index_rows(sets: Sequence[Mapping[str, Any]], source_rows: Iterable[Mapping[str, Any]], *, through_date: str | None = None, accepted_dates: Iterable[str] | None = None) -> list[dict[str, Any]]:
    # BLOCKER 1: quality filtering happens HERE, before any observation is
    # assembled and therefore before build_chain_linked_history runs. A
    # DEGRADED date must contribute zero mathematical influence to later
    # dates; filtering persisted output afterwards would still have chained
    # Aug 19's daily return off Aug 18.
    accepted = None if accepted_dates is None else {str(day)[:10] for day in accepted_dates}
    by_scope_date_set: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    all_dates: set[str] = set()
    for row in source_rows:
        scope, day, set_id = str(row.get("value_scope")), str(row.get("snapshot_date"))[:10], str(row.get("set_id"))
        if accepted is not None and day not in accepted:
            continue
        if scope in ("standard", "top10") and (through_date is None or day <= through_date):
            by_scope_date_set[(scope, day, set_id)] = row
            all_dates.add(day)
```

Leave the remainder of the function unchanged.

Then thread the parameter through `build_market_index_history`:

```python
def build_market_index_history(client: Any, *, through_date: str | None = None, accepted_dates: Iterable[str] | None = None) -> list[dict[str, Any]]:
    sets = resolve_eligible_sets(client)
    return build_index_rows(sets, _paged_source_rows(client, [str(row["id"]) for row in sets]), through_date=through_date, accepted_dates=accepted_dates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/services/test_market_index_quality_chain_math.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Confirm no existing index behaviour regressed**

Run: `python -m pytest backend/tests/unit/db/services/test_pokemon_market_index_service.py backend/tests/unit/domain/test_pokemon_market_index.py -v`
Expected: PASS — `accepted_dates=None` is the default, so existing callers are untouched.

- [ ] **Step 6: Commit**

```bash
git add backend/db/services/pokemon_market_index_service.py \
        backend/tests/unit/db/services/test_market_index_quality_chain_math.py
git commit -m "fix(market): filter quality dates before chain-link math"
```

---

### Task 5: Market publication gate

**Files:**
- Create: `backend/db/services/market_publication_gate.py`
- Test: `backend/tests/unit/db/services/test_market_publication_gate.py`

**Interfaces:**
- Consumes: Task 3's statuses, `evaluate_market_date_quality`, `persist_market_date_quality`, `resolve_latest_accepted_market_date`.
- Produces:
  - `MARKET_GATE_DEFERRED_EXIT_CODE = 3`
  - `MARKET_FORCE_PUBLISH_REJECTION = "Market Date Quality cannot be overridden with --force-publish"`
  - `class MarketForcePublishRejected(SystemExit)`
  - `MarketGateDecision` dataclass: `allowed: bool`, `status: str`, `market_date: str | None`, `reason: str`, `reason_code: str`, `evaluation: dict | None`
  - `MarketGateEnforcement` dataclass: `decision`, `proceed: bool`, `exit_code: int`
  - `enforce_market_publication_gate(client, *, commit, market_date=None, force_publish=False, entry_point="Market publication", persist=True) -> MarketGateEnforcement`
  - `add_market_gate_args(parser)` — registers `--market-date` only when absent.

Reuses the existing deferral convention (exit 3, a `PUBLICATION_DEFERRED` marker line) so operators and the shell wrapper read Market deferrals the same way.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/db/services/test_market_publication_gate.py
import pytest

from backend.db.services import market_publication_gate as gate
from backend.db.services.market_date_quality import (
    STATUS_DEGRADED, STATUS_INCOMPLETE, STATUS_READY,
)


class _Recorder:
    """Captures every write so tests can assert ZERO artifact upserts."""

    def __init__(self):
        self.upserts = []

    def table(self, name):
        recorder = self

        class _T:
            def upsert(self, rows, **_k):
                recorder.upserts.append((name, rows))
                return self

            def execute(self):
                class _R:
                    data = []
                return _R()
        return _T()


def _stub(monkeypatch, status, market_date="2026-08-19"):
    evaluation = {"marketDate": market_date, "status": status,
                  "contractVersion": "pokemon-market-date-quality-v1",
                  "cohortSetCount": 22,
                  "qualifyingSetCount": 22 if status == STATUS_READY else 13,
                  "missingSetIds": [], "cohortFingerprint": "fp", "evidence": {}}
    monkeypatch.setattr(gate, "evaluate_market_date_quality",
                        lambda *a, **k: evaluation)
    monkeypatch.setattr(gate, "persist_market_date_quality", lambda *a, **k: 1)
    monkeypatch.setattr(gate, "resolve_latest_accepted_market_date",
                        lambda *a, **k: "2026-08-17")
    return evaluation


def test_ready_allows_commit(monkeypatch):
    _stub(monkeypatch, STATUS_READY)
    result = gate.enforce_market_publication_gate(_Recorder(), commit=True)
    assert result.proceed is True
    assert result.exit_code == 0
    assert result.decision.status == STATUS_READY


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_statuses_defer_with_exit_code_three(monkeypatch, status):
    _stub(monkeypatch, status)
    result = gate.enforce_market_publication_gate(_Recorder(), commit=True)
    assert result.proceed is False
    assert result.exit_code == gate.MARKET_GATE_DEFERRED_EXIT_CODE == 3
    assert result.decision.allowed is False


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_force_publish_is_explicitly_rejected(monkeypatch, status):
    _stub(monkeypatch, status)
    with pytest.raises(gate.MarketForcePublishRejected) as excinfo:
        gate.enforce_market_publication_gate(
            _Recorder(), commit=True, force_publish=True)
    assert gate.MARKET_FORCE_PUBLISH_REJECTION in str(excinfo.value)


def test_force_publish_is_rejected_even_when_ready(monkeypatch):
    # The flag is meaningless for Market publication; never silently ignore it.
    _stub(monkeypatch, STATUS_READY)
    with pytest.raises(gate.MarketForcePublishRejected):
        gate.enforce_market_publication_gate(
            _Recorder(), commit=True, force_publish=True)


def test_dry_run_reports_without_writing(monkeypatch, capsys):
    _stub(monkeypatch, STATUS_INCOMPLETE)
    client = _Recorder()
    result = gate.enforce_market_publication_gate(client, commit=False)
    assert result.proceed is True
    assert client.upserts == [], "dry-run must not write artifacts"
    assert STATUS_INCOMPLETE in capsys.readouterr().out


def test_blocked_commit_persists_quality_state_but_no_artifacts(monkeypatch):
    evaluation = _stub(monkeypatch, STATUS_INCOMPLETE)
    persisted = []
    monkeypatch.setattr(gate, "persist_market_date_quality",
                        lambda client, ev: persisted.append(ev) or 1)
    client = _Recorder()
    gate.enforce_market_publication_gate(client, commit=True)
    assert persisted == [evaluation], "quality state is diagnostic, not publication"
    assert client.upserts == [], "zero Market artifact upserts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_market_publication_gate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/db/services/market_publication_gate.py
"""Market-only publication gate.

Parallel to - never a replacement for - ``publication_gate.py``. The 167-set
batch gate keeps its authority over RIP/rankings/set-page/non-Market surfaces.
This gate answers one question: may the Market surface publish for a date,
judged solely on the canonical Market cohort?

``--force-publish`` is REJECTED here rather than ignored, so an operator can
never believe they deliberately bypassed Market quality when the flag did
nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from backend.db.services.market_date_quality import (
    ACCEPTED_STATUSES,
    STATUS_DEGRADED,
    STATUS_INCOMPLETE,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
    evaluate_market_date_quality,
    persist_market_date_quality,
    resolve_latest_accepted_market_date,
)

logger = logging.getLogger(__name__)

_GATE_TAG = "[market-quality-gate]"

MARKET_GATE_DEFERRED_EXIT_CODE = 3
DEFERRAL_MARKER = "PUBLICATION_DEFERRED"

MARKET_FORCE_PUBLISH_REJECTION = (
    "Market Date Quality cannot be overridden with --force-publish")

REASON_ALLOWED_READY = "market_allowed_ready"
REASON_ALLOWED_LEGACY_VERIFIED = "market_allowed_legacy_verified"
REASON_BLOCKED_INCOMPLETE = "market_blocked_incomplete"
REASON_BLOCKED_DEGRADED = "market_blocked_degraded"
REASON_BLOCKED_NO_EVIDENCE = "market_blocked_no_quality_evidence"

_REASON_BY_STATUS = {
    STATUS_READY: REASON_ALLOWED_READY,
    STATUS_LEGACY_VERIFIED: REASON_ALLOWED_LEGACY_VERIFIED,
    STATUS_INCOMPLETE: REASON_BLOCKED_INCOMPLETE,
    STATUS_DEGRADED: REASON_BLOCKED_DEGRADED,
}


class MarketForcePublishRejected(SystemExit):
    """Raised when --force-publish is aimed at a Market quality-gated command."""

    def __init__(self, message: str = MARKET_FORCE_PUBLISH_REJECTION):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


@dataclass
class MarketGateDecision:
    allowed: bool
    status: str
    market_date: Optional[str]
    reason: str
    reason_code: str
    evaluation: Optional[dict] = None


@dataclass
class MarketGateEnforcement:
    decision: MarketGateDecision
    proceed: bool
    exit_code: int


def add_market_gate_args(parser: Any) -> None:
    """Register Market gate flags, tolerating a parser that already has them."""
    existing = {action.dest for action in getattr(parser, "_actions", [])}
    if "market_date" not in existing:
        parser.add_argument(
            "--market-date",
            help="America/Phoenix market date whose Market Date Quality gates publication")


def resolve_market_publication_date(client: Any, requested: Optional[str]) -> Optional[str]:
    if requested:
        return str(requested)[:10]
    return resolve_latest_accepted_market_date(client)


def enforce_market_publication_gate(
    client: Any,
    *,
    commit: bool,
    market_date: Optional[str] = None,
    force_publish: bool = False,
    entry_point: str = "Market publication",
    persist: bool = True,
) -> MarketGateEnforcement:
    """Evaluate Market Date Quality once per invocation and decide.

    Never consults ``pokemon_scrape_batches``: once Market quality has
    independently proven READY, the full 167-set batch is NOT an additional
    requirement.
    """
    if force_publish:
        logger.error("%s %s (entry_point=%s)", _GATE_TAG,
                     MARKET_FORCE_PUBLISH_REJECTION, entry_point)
        raise MarketForcePublishRejected()

    target = str(market_date)[:10] if market_date else None
    if target is None:
        raise ValueError(
            f"{entry_point}: --market-date is required when no accepted Market date exists")

    evaluation = evaluate_market_date_quality(client, target)
    status = str(evaluation.get("status") or "")
    reason_code = _REASON_BY_STATUS.get(status, REASON_BLOCKED_NO_EVIDENCE)
    allowed = status in ACCEPTED_STATUSES

    if allowed:
        reason = (f"Market cohort {evaluation['qualifyingSetCount']}/"
                  f"{evaluation['cohortSetCount']} qualifying for {target}; status={status}")
    else:
        reason = (f"Market cohort {evaluation['qualifyingSetCount']}/"
                  f"{evaluation['cohortSetCount']} qualifying for {target}; status={status}; "
                  f"missing={list(evaluation.get('missingSetIds') or [])[:10]}")

    decision = MarketGateDecision(allowed=allowed, status=status, market_date=target,
                                  reason=reason, reason_code=reason_code,
                                  evaluation=dict(evaluation))

    if not commit:
        # Dry-run: evaluate and REPORT only. No quality write, no artifact write.
        print(f"{entry_point}: Market Date Quality (dry-run) [{reason_code}] "
              f"status={status} allowed={allowed}: {reason}")
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)

    # Commit mode. The quality row is durable diagnostic STATE, explicitly not
    # Market artifact publication, so it is written even on a blocked date.
    if persist:
        try:
            persist_market_date_quality(client, evaluation)
        except Exception as exc:  # diagnostics must never gate publication
            logger.warning("%s could not persist quality state for %s: %s",
                           _GATE_TAG, target, exc)

    if allowed:
        logger.info("%s publication ALLOWED for %s (status=%s)", _GATE_TAG, target, status)
        print(f"{entry_point}: Market Date Quality [{reason_code}] status={status}: {reason}")
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)

    logger.warning("%s publication BLOCKED for %s (status=%s)", _GATE_TAG, target, status)
    for line in (
        f"{entry_point}: Market publication gate CLOSED [{reason_code}]: {reason}",
        (f"{DEFERRAL_MARKER} entry_point={entry_point!r} market_date={target} "
         f"market_quality_status={status} reason_code={reason_code}"),
        "preserving previous good public Market authority; no promotion performed",
    ):
        print(line)
    return MarketGateEnforcement(
        decision=decision, proceed=False, exit_code=MARKET_GATE_DEFERRED_EXIT_CODE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/unit/db/services/test_market_publication_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/services/market_publication_gate.py \
        backend/tests/unit/db/services/test_market_publication_gate.py
git commit -m "feat(market): add market-only publication gate rejecting --force-publish"
```

---

### Task 6: Wire the Market index history entry point

**Files:**
- Modify: `backend/scripts/build_pokemon_market_index_history.py`
- Test: covered by Task 7's integration tests; this task's own check is the existing suite.

**Interfaces:**
- Consumes: Task 4's `accepted_dates`, Task 5's `enforce_market_publication_gate`, Task 3's `accepted_market_dates`.
- Produces: `build(client, *, market_date=None, backfill=False, from_date=None, commit=False, accepted_dates=None)` and a `main()` that returns/propagates exit code 3 on a blocked Market date.

- [ ] **Step 1: Apply the change**

Add imports:

```python
from backend.db.services.market_date_quality import accepted_market_dates
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected, add_market_gate_args, enforce_market_publication_gate,
)
```

Register the flags in `parser()` (after the existing `--from-date` line):

```python
    add_market_gate_args(p)
    p.add_argument("--force-publish", action="store_true",
                   help="Rejected for Market publication; Market Date Quality cannot be overridden")
```

Thread accepted dates into `build`:

```python
def build(client, *, market_date=None, backfill=False, from_date=None, commit=False, accepted_dates=None):
    rows = build_market_index_history(client, through_date=market_date, accepted_dates=accepted_dates)
```

Leave the rest of `build` unchanged. Replace `main()`:

```python
def main():
    args = parser().parse_args()
    client = get_client()
    try:
        gate = enforce_market_publication_gate(
            client, commit=bool(args.commit), market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Pokemon Market index history")
    except MarketForcePublishRejected as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)
    # BLOCKER 1: the accepted-date set is resolved BEFORE the build so that
    # chain-link math never sees a DEGRADED or INCOMPLETE date.
    accepted = accepted_market_dates(client, through_date=args.market_date)
    accepted.add(str(gate.decision.market_date)[:10])
    try:
        summary = build(client, market_date=args.market_date, backfill=args.backfill,
                        from_date=args.from_date, commit=args.commit,
                        accepted_dates=accepted)
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True)); raise SystemExit(1) from exc
    summary["marketQualityStatus"] = gate.decision.status
    print(json.dumps(summary, indent=2, sort_keys=True))
```

- [ ] **Step 2: Verify the module still imports and the CLI parses**

Run: `python -c "from backend.scripts.build_pokemon_market_index_history import parser, build; parser().parse_args(['--dry-run','--market-date','2026-08-19']); print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Run the existing market suites**

Run: `python -m pytest backend/tests/unit/db/services/test_pokemon_market_index_service.py backend/tests/unit/db/services/test_market_index_quality_chain_math.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/build_pokemon_market_index_history.py
git commit -m "feat(market): gate index history on Market Date Quality"
```

---

### Task 7: Wire the dashboard and Global Set Value entry points

**Files:**
- Modify: `backend/scripts/build_pokemon_market_dashboard_snapshots.py:88-96`
- Modify: `backend/scripts/build_pokemon_explore_set_value_snapshot.py:99-106`

**Interfaces:**
- Consumes: Task 5's gate.
- Produces: both commands defer with exit 3 on INCOMPLETE/DEGRADED and reject `--force-publish`, while the existing 167-set `enforce_cli_publication_gate` call is **left in place** for their non-Market responsibilities.

The Market gate is evaluated **first**. When Market quality is READY the command proceeds on Market authority alone — the batch gate must not be applied as an additional requirement to Market artifacts.

- [ ] **Step 1: Change the dashboard entry point**

In `backend/scripts/build_pokemon_market_dashboard_snapshots.py`, add to the imports beside the existing `publication_gate` import:

```python
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected, enforce_market_publication_gate,
)
```

Replace the gate block at lines 88-96 with:

```python
    # Market Date Quality is the authority for Market artifacts. It is
    # evaluated on the canonical Market cohort alone: an unrelated non-Market
    # failure in the 167-set batch must not hold the Market surface hostage.
    try:
        market_gate = enforce_market_publication_gate(
            client,
            commit=commit,
            market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Pokemon Market dashboard snapshots",
        )
    except MarketForcePublishRejected as exc:
        print(str(exc))
        return 2
    if not market_gate.proceed:
        return market_gate.exit_code
```

- [ ] **Step 2: Change the Global Set Value entry point**

In `backend/scripts/build_pokemon_explore_set_value_snapshot.py`, add:

```python
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected, enforce_market_publication_gate,
)
```

Replace lines 99-103 (the `enforce_cli_publication_gate` call, the `gate.proceed` check, and the `market_date` resolution) with:

```python
    try:
        gate = enforce_market_publication_gate(
            client, commit=bool(args.commit), market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Global Market Set Value snapshot")
    except MarketForcePublishRejected as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)
    market_date = args.market_date or gate.decision.market_date
```

Leave the following `if not market_date:` block and everything after it unchanged.

- [ ] **Step 3: Verify both modules import**

Run: `python -c "import backend.scripts.build_pokemon_market_dashboard_snapshots as d, backend.scripts.build_pokemon_explore_set_value_snapshot as s; print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Run their existing suites**

Run: `python -m pytest backend/tests/unit/scripts/test_build_pokemon_market_dashboard_snapshots.py -v`
Expected: PASS. If a test asserts the old batch-gate deferral text on a Market path, update that test to the Market gate's `market_blocked_*` reason code — do not weaken the gate to satisfy it.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/build_pokemon_market_dashboard_snapshots.py \
        backend/scripts/build_pokemon_explore_set_value_snapshot.py
git commit -m "feat(market): gate dashboard and set value publication on Market Date Quality"
```

---

### Task 8: Publication integration tests (Blocker 4, cases 1-5, 9, 10)

**Files:**
- Create: `backend/tests/unit/scripts/test_market_publication_integration.py`

**Interfaces:**
- Consumes: every prior task. Tests call the real `main()` of the three Market entry points.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/scripts/test_market_publication_integration.py
"""Blocker 4: exercise the REAL Market publication entry points.

Every case asserts on artifact upserts actually reaching the client, not on
service-helper return values.
"""

import pytest

import backend.scripts.build_pokemon_explore_set_value_snapshot as set_value
import backend.scripts.build_pokemon_market_index_history as index_history
from backend.db.services import market_publication_gate as gate
from backend.db.services.market_date_quality import (
    STATUS_DEGRADED, STATUS_INCOMPLETE, STATUS_READY,
)

MARKET_ARTIFACT_TABLES = {
    "pokemon_market_index_daily_history",
    "pokemon_market_dashboard_snapshots",
    "pokemon_explore_set_value_snapshot",
    "pokemon_set_value_daily_history",
}
QUALITY_TABLE = "pokemon_market_date_quality"


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, client, name):
        self._client, self._name = client, name

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    def upsert(self, rows, **_k):
        self._client.upserts.append((self._name, list(rows)))
        return self

    def execute(self):
        return _Result(list(self._client.rows.get(self._name, [])))


class _Client:
    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.upserts = []

    def table(self, name):
        return _Table(self, name)

    @property
    def artifact_upserts(self):
        return [entry for entry in self.upserts if entry[0] in MARKET_ARTIFACT_TABLES]

    @property
    def quality_upserts(self):
        return [entry for entry in self.upserts if entry[0] == QUALITY_TABLE]


def _force_status(monkeypatch, status, market_date="2026-08-19"):
    evaluation = {"marketDate": market_date, "status": status,
                  "contractVersion": "pokemon-market-date-quality-v1",
                  "cohortSetCount": 22,
                  "qualifyingSetCount": 22 if status == STATUS_READY else 13,
                  "missingSetIds": [] if status == STATUS_READY else ["set-x"],
                  "cohortFingerprint": "fp", "evidence": {}}
    monkeypatch.setattr(gate, "evaluate_market_date_quality", lambda *a, **k: evaluation)
    monkeypatch.setattr(gate, "resolve_latest_accepted_market_date",
                        lambda *a, **k: "2026-08-17")
    return evaluation


# ---------------------------------------------------------------- cases 1 & 2

@pytest.mark.parametrize("full_batch_status", ["complete", "incomplete"])
def test_ready_allows_market_writes_regardless_of_full_batch(monkeypatch, full_batch_status):
    """Case 1 and case 2.

    164/167 with 3 unrelated deterministic failures must NOT block a 22/22
    Market cohort. The full batch is not an additional requirement.
    """
    _force_status(monkeypatch, STATUS_READY)
    client = _Client({"pokemon_scrape_batches": [{
        "id": 7, "market_date": "2026-08-19", "status": full_batch_status,
        "promoted_at": None if full_batch_status == "incomplete" else "2026-08-19T12:00:00Z",
        "missing_set_count": 3 if full_batch_status == "incomplete" else 0,
        "expected_set_count": 167}]})

    result = gate.enforce_market_publication_gate(
        client, commit=True, market_date="2026-08-19",
        entry_point="Pokemon Market index history")

    assert result.proceed is True
    assert result.exit_code == 0
    assert result.decision.status == STATUS_READY


# ------------------------------------------------------------- cases 3, 4, 9

@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_status_writes_zero_market_artifacts(monkeypatch, status):
    """Cases 3 and 4, across all three real entry points."""
    _force_status(monkeypatch, status)

    for module, argv in (
        (index_history, ["prog", "--commit", "--market-date", "2026-08-19"]),
        (set_value, ["prog", "--commit", "--market-date", "2026-08-19"]),
    ):
        client = _Client()
        monkeypatch.setattr(module, "get_client", lambda client=client: client)
        monkeypatch.setattr("sys.argv", argv)

        with pytest.raises(SystemExit) as excinfo:
            module.main()

        assert excinfo.value.code == 3, f"{module.__name__} must defer with exit 3"
        assert client.artifact_upserts == [], (
            f"{module.__name__} wrote Market artifacts on {status}")


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_status_still_persists_quality_state(monkeypatch, status):
    """Case 3: quality state is durable diagnostics, not publication."""
    _force_status(monkeypatch, status)
    client = _Client()
    gate.enforce_market_publication_gate(client, commit=True, market_date="2026-08-19")
    assert len(client.quality_upserts) == 1
    assert client.artifact_upserts == []


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_force_publish_does_not_publish(monkeypatch, status):
    """Case 9: explicit rejection, and definitely no writes."""
    _force_status(monkeypatch, status)
    client = _Client()
    monkeypatch.setattr(index_history, "get_client", lambda: client)
    monkeypatch.setattr("sys.argv",
                        ["prog", "--commit", "--market-date", "2026-08-19", "--force-publish"])

    with pytest.raises(SystemExit) as excinfo:
        index_history.main()

    assert excinfo.value.code == 2
    assert client.artifact_upserts == []


def test_dry_run_on_blocked_date_writes_nothing(monkeypatch):
    _force_status(monkeypatch, STATUS_INCOMPLETE)
    client = _Client()
    gate.enforce_market_publication_gate(client, commit=False, market_date="2026-08-19")
    assert client.upserts == []


# ------------------------------------------------------------------- case 10

def test_general_publication_authority_is_unweakened():
    """Case 10: the 167-set gate is untouched for non-Market surfaces."""
    from backend.db.services import publication_gate

    client = _Client({"pokemon_scrape_batches": [{
        "id": 7, "market_date": "2026-08-19", "status": "incomplete",
        "promoted_at": None, "missing_set_count": 3, "expected_set_count": 167}]})

    decision = publication_gate.evaluate_publication_gate(
        client, market_date="2026-08-19", mode=publication_gate.MODE_REQUIRED)

    assert decision.allowed is False
    assert decision.reason_code == publication_gate.REASON_BLOCKED_INCOMPLETE
```

- [ ] **Step 2: Run test to verify it fails or reveals wiring gaps**

Run: `python -m pytest backend/tests/unit/scripts/test_market_publication_integration.py -v`
Expected: initially FAIL. Fix the *wiring* in Tasks 6–7 until it passes; never relax an assertion to make a case go green.

- [ ] **Step 3: Add case 5 (DEGRADED rows are preserved, not deleted)**

Append:

```python
def test_existing_degraded_rows_are_never_deleted(monkeypatch):
    """Case 5: Aug 18 evidence stays in storage; it is excluded, not erased."""
    from backend.db.services.pokemon_market_index_service import build_index_rows

    _force_status(monkeypatch, STATUS_READY)
    stored = [{"market_date": "2026-08-18", "index_key": "raw"}]
    client = _Client({"pokemon_market_index_daily_history": list(stored)})

    gate.enforce_market_publication_gate(client, commit=True, market_date="2026-08-19")

    assert client.rows["pokemon_market_index_daily_history"] == stored
    assert not any(entry[0] == "pokemon_market_index_daily_history"
                   for entry in client.upserts), "no delete or rewrite of Aug 18"

    sets = [{"id": "set-a", "canonical_key": "a", "release_date": "2020-01-01"}]
    source = [{"set_id": "set-a", "snapshot_date": day, "set_value": 100.0,
               "priced_card_count": 5, "value_scope": scope, "source": "t",
               "updated_at": f"{day}T00:00:00Z"}
              for day in ("2026-08-17", "2026-08-18", "2026-08-19")
              for scope in ("standard", "top10")]
    rows = build_index_rows(sets, source, accepted_dates={"2026-08-17", "2026-08-19"})
    assert "2026-08-18" not in {row["market_date"] for row in rows}
```

- [ ] **Step 4: Run the full file**

Run: `python -m pytest backend/tests/unit/scripts/test_market_publication_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/scripts/test_market_publication_integration.py
git commit -m "test(market): integration coverage at real Market publication entry points"
```

---

### Task 9: LEGACY_VERIFIED and latest-authority tests (Blocker 4, cases 6, 7, 8)

**Files:**
- Modify: `backend/tests/unit/db/services/test_market_date_quality.py`

**Interfaces:**
- Consumes: Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/db/services/test_market_date_quality.py`:

```python
def test_case6_aug19_chains_directly_off_aug17():
    """Case 6, restated at the quality+math seam."""
    from backend.db.services.pokemon_market_index_service import build_index_rows

    sets = [{"id": "s", "canonical_key": "s", "release_date": "2020-01-01"}]

    def source(aug18):
        return [{"set_id": "s", "snapshot_date": day, "set_value": value,
                 "priced_card_count": 3, "value_scope": scope, "source": "t",
                 "updated_at": f"{day}T00:00:00Z"}
                for day, value in (("2026-08-17", 200.0), ("2026-08-18", aug18),
                                   ("2026-08-19", 240.0))
                for scope in ("standard", "top10")]

    accepted = {"2026-08-17", "2026-08-19"}
    low = build_index_rows(sets, source(1.0), accepted_dates=accepted)
    high = build_index_rows(sets, source(1_000_000.0), accepted_dates=accepted)

    def aug19(rows):
        return next(r for r in rows
                    if r["market_date"] == "2026-08-19" and r["index_key"] == "raw")

    assert aug19(low)["previous_market_date"] == "2026-08-17"
    assert aug19(low)["normalized_index_value"] == aug19(high)["normalized_index_value"]
    assert aug19(low)["normalized_index_value"] == 120.0  # 100 * 240/200


def test_case7_legacy_verified_date_participates_in_chain_and_backfill():
    from backend.db.services.market_date_quality import ACCEPTED_STATUSES
    assert STATUS_LEGACY_VERIFIED in ACCEPTED_STATUSES

    client = _PagingClient([
        {"market_date": "2026-08-16", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-17", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
    ])
    assert mdq.accepted_market_dates(client) == {"2026-08-16", "2026-08-17"}


def test_case8_missing_evidence_after_cutoff_is_never_laundered():
    for later, expected in ((False, STATUS_INCOMPLETE), (True, STATUS_DEGRADED)):
        result = _classify(market_date="2026-08-20", qualifying_set_ids=set(),
                           has_later_accepted_date=later,
                           legacy_allowlist=frozenset({"2026-08-20"}))
        assert result["status"] == expected
        assert result["status"] != STATUS_LEGACY_VERIFIED


def test_degraded_date_never_wins_latest_public_authority():
    client = _PagingClient([
        {"market_date": "2026-08-17", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
        {"market_date": "2026-08-19", "status": STATUS_READY},
    ])
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-19"


def test_latest_authority_falls_back_to_prior_good_date_when_current_is_blocked():
    client = _PagingClient([
        {"market_date": "2026-08-17", "status": STATUS_READY},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
    ])
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-17"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/unit/db/services/test_market_date_quality.py -v`
Expected: FAIL only where wiring is genuinely missing; otherwise PASS.

- [ ] **Step 3: Fix any gaps and re-run**

Run: `python -m pytest backend/tests/unit/db/services/test_market_date_quality.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/db/services/test_market_date_quality.py
git commit -m "test(market): cover LEGACY_VERIFIED, cutoff laundering, and latest authority"
```

---

### Task 10: Full-suite regression

**Files:** none modified unless a regression surfaces.

- [ ] **Step 1: Run every market, gate, and publication suite**

```bash
python -m pytest \
  backend/tests/unit/db/services/test_market_run_evidence.py \
  backend/tests/unit/db/services/test_market_date_quality.py \
  backend/tests/unit/db/services/test_market_publication_gate.py \
  backend/tests/unit/db/services/test_market_index_quality_chain_math.py \
  backend/tests/unit/db/services/test_publication_gate.py \
  backend/tests/unit/db/services/test_promoted_market_date_resolution.py \
  backend/tests/unit/db/services/test_pokemon_market_index_service.py \
  backend/tests/unit/domain/test_pokemon_market_index.py \
  backend/tests/unit/scripts/test_market_publication_integration.py \
  backend/tests/unit/scripts/test_build_pokemon_market_dashboard_snapshots.py \
  backend/tests/unit/scripts/test_build_pokemon_public_snapshots.py \
  backend/tests/unit/scripts/test_publication_lifecycle_contract.py \
  -v
```

Expected: all PASS.

- [ ] **Step 2: Run the whole backend unit suite for collateral damage**

Run: `python -m pytest backend/tests/unit -q`
Expected: no NEW failures versus `git stash && python -m pytest backend/tests/unit -q`. Record the baseline before claiming success.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "test(market): reconcile suites with Market Date Quality authority"
```

---

### Task 11: Read-only production verification (operator-run)

**Files:** none. This task mutates nothing.

This is the only step that touches production, and it is **read-only**. It exists because one fact could not be settled from the repo: whether the nine reconciled Market sets' Aug 19 runs carry `queue_job_id` or rely on the Blocker 3 fallback. Both paths are implemented; this confirms which one production actually uses and that Aug 19 really evaluates READY.

- [ ] **Step 1: Confirm the qualifying-run evidence resolves 22/22**

Run this read-only SQL against production:

```sql
SELECT r.id, r.queue_job_id, j.set_id AS queue_linked_set_id,
       r.metadata ->> 'set_id'   AS metadata_set_id,
       r.metadata ->> 'set_filter' AS metadata_set_filter,
       r.items_succeeded, r.items_failed,
       r.metadata ->> 'sourceCoverageRatio'        AS coverage,
       r.metadata ->> 'acceptedVariantGroups'      AS accepted,
       r.metadata ->> 'positiveNmObservationCount' AS positive
FROM public.scrape_job_runs r
LEFT JOIN public.scrape_jobs j ON j.id = r.queue_job_id
WHERE r.market_date = '2026-08-19'
  AND r.job_name = 'pokemon_set_scrape'
  AND r.source_system = 'tcgplayer'
  AND r.job_type = 'price_scrape'
  AND r.entity_type = 'set'
  AND r.status = 'success'
ORDER BY r.id;
```

Expected: every Market cohort set is covered by a row whose identity resolves through `queue_linked_set_id` **or** `metadata_set_id`.

- [ ] **Step 2: If any qualifying run resolves through neither column, STOP**

If a Market set's only Aug 19 evidence carries a NULL `queue_job_id` **and** a NULL `metadata.set_id` — only a `set_filter` — then `qualifying_set_ids_for_date` will not credit it, Aug 19 evaluates INCOMPLETE, and Market publication correctly stays blocked. Do not loosen `resolve_run_set_id` to read `set_filter` without an explicit decision from the operator: `set_filter` is an operator-supplied filter list, not a set identity, and the spec forbids inferring identity. Report the finding and stop.

- [ ] **Step 3: Dry-run the three entry points against production (read-only)**

```bash
python -m backend.scripts.build_pokemon_market_index_history --dry-run --market-date 2026-08-19
python -m backend.scripts.build_pokemon_explore_set_value_snapshot --dry-run --market-date 2026-08-19
python -m backend.scripts.build_pokemon_market_dashboard_snapshots --dry-run --market-date 2026-08-19
```

Expected on each: a line reporting `status=READY` and `allowed=True`, and zero writes.

- [ ] **Step 4: Confirm Aug 18 classifies DEGRADED**

Run: `python -m backend.scripts.build_pokemon_market_index_history --dry-run --market-date 2026-08-18`
Expected: `status=DEGRADED`, `allowed=False`.

- [ ] **Step 5: Confirm the general gate is still closed**

Run: `python -m backend.scripts.build_pokemon_public_snapshots --dry-run`
Expected: still reports `blocked_incomplete` for the 167-set batch. The separation is intentional and must survive this change.

---

## Self-Review

**Spec coverage:**
- Market quality contract / cohort / predicate -> Tasks 2, 3
- Statuses incl. Aug 18 DEGRADED, Aug 19 READY -> Tasks 3, 9, 11
- Blocker 1 (filter before chain math) -> Task 4, regression in Tasks 4, 8, 9
- Blocker 2 (paginated quality history) -> Task 3 Step 5
- Blocker 3 (run resolution fallback + all six required cases) -> Task 2
- Blocker 4 READY / INCOMPLETE / DEGRADED / LEGACY_VERIFIED behaviours -> Tasks 3, 5, 6, 7
- Blocker 4 `--force-publish` explicit rejection -> Task 5, integration case 9 in Task 8
- Blocker 4 integration cases 1-10 -> Tasks 8 and 9
- Public latest authority -> Task 3 `resolve_latest_accepted_market_date`, tests in Task 9
- Prohibitions -> Global Constraints; Task 11 is read-only

**Open item deliberately carried:** whether production's Aug 19 reconciliation runs expose `metadata.set_id`. Task 11 Step 2 is the explicit stop-and-report gate rather than a silent loosening of identity rules.
