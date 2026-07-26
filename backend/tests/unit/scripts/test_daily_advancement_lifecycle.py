"""Two-day daily-advancement lifecycle at the CLI boundary.

The recurring production symptom was not a one-off stale payload: the daily
pipeline failed to advance one or more public snapshot families when a new
market date became available, and nothing surfaced it. This test drives the
REAL publication gate (against a fake batch table implementing the real cohort
contract) and the REAL publisher CLI entry points across a market-date rollover.

Day 1 (2026-07-25, cohort complete)  -> everything publishes July 25, exit 0.
Day 2 (2026-07-26, cohort incomplete) -> gate closes, ZERO writes, ZERO cache
                                          invalidations, exit 3, July 25 rows
                                          preserved.
Day 2 after the cohort completes      -> the bounded automatic retry publishes
                                          July 26 across every family, rebuilds
                                          the set page after its market
                                          dependencies, invalidates the caches,
                                          exits 0, and leaves nothing on July 25.
"""

import sys

import pytest

from backend.db.services import set_publication_revalidation as revalidation
from backend.scripts import build_pokemon_market_dashboard_snapshots as market_cmd
from backend.scripts import build_pokemon_set_page_snapshots as page_cmd
from backend.scripts import refresh_stale_public_snapshots as refresh

SETS = [
    {"id": "uuid-1", "canonical_key": "alpha", "pokemon_api_set_id": "sv1", "name": "Alpha"},
    {"id": "uuid-2", "canonical_key": "beta", "pokemon_api_set_id": "sv2", "name": "Beta"},
]


# --------------------------------------------------------------------------- #
# A fake world: the scrape-batch cohort + the published snapshot rows.
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, data):
        self.data = data


class _BatchQuery:
    def __init__(self, world):
        self._world = world
        self._market_date = None

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        if field == "market_date":
            self._market_date = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        batch = self._world.batch
        if batch is None:
            return _Result([])
        if self._market_date is not None and batch["market_date"] != self._market_date:
            return _Result([])
        return _Result([dict(batch)])


class _World:
    """Source state + published snapshot rows for one simulated day."""

    def __init__(self):
        self.batch = None
        self.market_date = None
        self.simulation_date = "2026-07-17"  # deliberately lagging all along
        self.rows = {}          # (table, key) -> row
        self.revalidations = [] # publish-success cache invalidations
        self.write_log = []     # ordered table writes

    # --- batch cohort -----------------------------------------------------
    def open_cohort(self, market_date, *, complete):
        self.market_date = market_date
        self.batch = {
            "id": f"batch-{market_date}",
            "market_date": market_date,
            "status": "complete" if complete else "running",
            "promoted_at": f"{market_date}T23:00:00+00:00" if complete else None,
            "missing_set_count": 0 if complete else 3,
            "expected_set_count": len(SETS),
            "succeeded_set_count": len(SETS) if complete else 0,
            "failed_set_count": 0,
        }

    def complete_cohort(self):
        self.batch["status"] = "complete"
        self.batch["promoted_at"] = f"{self.batch['market_date']}T23:30:00+00:00"
        self.batch["missing_set_count"] = 0
        self.batch["succeeded_set_count"] = len(SETS)

    # --- supabase-ish client ---------------------------------------------
    def table(self, table_name):
        if table_name == "pokemon_scrape_batches":
            return _BatchQuery(self)
        raise AssertionError(f"unexpected table read: {table_name}")

    # --- published state --------------------------------------------------
    def write(self, table, row, key):
        self.write_log.append(table)
        self.rows[(table, key)] = row

    def published_dates(self, table):
        return {key[1]: row.get("market_date") for key, row in self.rows.items() if key[0] == table}


@pytest.fixture
def world():
    return _World()


def _install(monkeypatch, world):
    """Wire the real CLIs to the fake world; builders stamp the cohort's date."""
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)  # real `required` mode

    def build_market(set_row, **_kwargs):
        market_date = world.market_date
        cards = {"set_id": set_row["id"], "market_date": market_date}
        dashboard = {
            "set_id": set_row["id"],
            "window_key": "365d",
            "market_date": market_date,
            # Section freshness is produced by the real contract helper so the
            # lifecycle test also proves market/simulation separation.
            "section_freshness": __import__(
                "backend.scripts.pokemon_snapshot_builders", fromlist=["x"]
            )._build_dashboard_section_freshness(
                built_at=f"{market_date}T23:59:00+00:00",
                advertised_market_date=market_date,
                set_value_source_date=market_date,
                top_chase_source_date=market_date,
                cards_snapshot_source_date=market_date,
                simulation_source_date=world.simulation_date,
            ),
        }
        history = [
            {"set_id": set_row["id"], "snapshot_date": market_date, "market_date": market_date}
        ]
        return cards, dashboard, history

    def market_upsert_row(_client, table, row, **_k):
        world.write(table, row, row["set_id"])

    def market_upsert_rows(_client, table, rows, **_k):
        for row in rows:
            world.write(table, row, row["set_id"])

    monkeypatch.setattr(market_cmd, "get_client", lambda: world)
    monkeypatch.setattr(market_cmd, "resolve_target_sets", lambda _c, _a: SETS)
    monkeypatch.setattr(market_cmd, "refresh_canonical_card_market_prices_for_set", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "build_coordinated_set_market_snapshot_rows", build_market)
    monkeypatch.setattr(market_cmd, "upsert_row", market_upsert_row)
    monkeypatch.setattr(market_cmd, "upsert_rows", market_upsert_rows)

    def build_page(set_row, client=None):
        # The set page embeds the market snapshot's date, so it must run AFTER
        # the coordinated market publication for that set.
        cards = world.rows.get(("pokemon_set_cards_snapshot_latest", set_row["id"])) or {}
        return {
            "set_id": set_row["id"],
            "market_date": cards.get("market_date"),
            "simulation_date": world.simulation_date,
        }

    monkeypatch.setattr(page_cmd, "get_client", lambda: world)
    monkeypatch.setattr(page_cmd, "resolve_target_sets", lambda _c, _a: SETS)
    monkeypatch.setattr(page_cmd, "build_set_page_snapshot_row", build_page)
    monkeypatch.setattr(
        page_cmd, "upsert_row", lambda _c, table, row, **_k: world.write(table, row, row["set_id"])
    )

    def record_revalidation(set_row, *, window=None, commit=True, seen=None):
        if not commit:
            return False
        identifiers = revalidation.resolve_set_revalidation_identifiers(set_row)
        if seen is not None:
            if identifiers[0] in seen:
                return False
            seen.add(identifiers[0])
        world.revalidations.append(
            {"set": identifiers[0], "tags": identifiers, "windows": revalidation.resolve_revalidation_windows(window)}
        )
        return True

    monkeypatch.setattr(market_cmd, "notify_set_publication", record_revalidation)
    monkeypatch.setattr(page_cmd, "notify_set_publication", record_revalidation)


def _publish_day(monkeypatch, world, *, gate_wait_attempts=0, on_wait=None):
    """One scheduled publication pass: gate -> market -> set pages."""
    slept = []

    def sleep(_delay):
        slept.append(_delay)
        if on_wait is not None:
            on_wait()

    gate = refresh._await_open_publication_gate(
        world,
        market_date=world.market_date,
        override=False,
        attempts=gate_wait_attempts,
        delay_seconds=600,
        sleep=sleep,
    )
    if not gate.allowed:
        return {"exit_code": 3, "waits": len(slept)}

    monkeypatch.setattr(
        sys,
        "argv",
        ["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit", "--delay-seconds", "0"],
    )
    market_exit = market_cmd.main()

    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])
    page_exit = page_cmd.main()

    return {"exit_code": market_exit or page_exit, "waits": len(slept)}


# --------------------------------------------------------------------------- #
# Day 1 — a complete cohort publishes the whole day.
# --------------------------------------------------------------------------- #
def test_day_one_publishes_every_family_for_the_completed_market_date(monkeypatch, world):
    _install(monkeypatch, world)
    world.open_cohort("2026-07-25", complete=True)

    result = _publish_day(monkeypatch, world)

    assert result["exit_code"] == 0
    for table in (
        "pokemon_set_cards_snapshot_latest",
        "pokemon_set_market_dashboard_snapshot_latest",
        "pokemon_set_top_chase_card_daily_history",
        "pokemon_set_page_snapshot_latest",
    ):
        assert world.published_dates(table) == {"uuid-1": "2026-07-25", "uuid-2": "2026-07-25"}, table

    # Coordinated write order, then the set page after its market dependencies.
    assert world.write_log.index("pokemon_set_page_snapshot_latest") > world.write_log.index(
        "pokemon_set_market_dashboard_snapshot_latest"
    )
    # Cache invalidation covered every published set (market + set page passes).
    assert {call["set"] for call in world.revalidations} == {"alpha", "beta"}

    # The lagging simulation is labeled, and never drags the market sections down.
    freshness = world.rows[("pokemon_set_market_dashboard_snapshot_latest", "uuid-1")]["section_freshness"]
    assert freshness["referenceDate"] == "2026-07-25"
    assert freshness["marketSectionsUniformlyCurrent"] is True
    assert freshness["openingProfitVsCost"] == {"sourceDate": "2026-07-17", "status": "stale"}


# --------------------------------------------------------------------------- #
# Day 2 — an incomplete cohort defers without touching anything.
# --------------------------------------------------------------------------- #
def test_day_two_incomplete_cohort_defers_and_preserves_day_one(monkeypatch, world):
    _install(monkeypatch, world)
    world.open_cohort("2026-07-25", complete=True)
    assert _publish_day(monkeypatch, world)["exit_code"] == 0
    writes_after_day_one = len(world.write_log)
    revalidations_after_day_one = len(world.revalidations)

    world.open_cohort("2026-07-26", complete=False)
    result = _publish_day(monkeypatch, world)

    assert result["exit_code"] == 3            # deferred, not failed
    assert len(world.write_log) == writes_after_day_one           # zero writes
    assert len(world.revalidations) == revalidations_after_day_one  # zero invalidations
    # The previous good July 25 publication is still being served.
    assert world.published_dates("pokemon_set_cards_snapshot_latest") == {
        "uuid-1": "2026-07-25",
        "uuid-2": "2026-07-25",
    }


# --------------------------------------------------------------------------- #
# Day 2 — the cohort completes and the bounded automatic retry advances the day.
# --------------------------------------------------------------------------- #
def test_day_two_automatic_retry_advances_every_family_after_the_cohort_completes(
    monkeypatch, world
):
    _install(monkeypatch, world)
    world.open_cohort("2026-07-25", complete=True)
    assert _publish_day(monkeypatch, world)["exit_code"] == 0
    world.revalidations.clear()

    # Publication starts while the day's cohort is still finishing.
    world.open_cohort("2026-07-26", complete=False)
    completion = {"pending": True}

    def cohort_finishes_during_the_wait():
        if completion["pending"]:
            completion["pending"] = False
            world.complete_cohort()

    result = _publish_day(
        monkeypatch, world, gate_wait_attempts=6, on_wait=cohort_finishes_during_the_wait
    )

    # No operator command was required: the same scheduled run published.
    assert result["exit_code"] == 0
    assert result["waits"] == 1  # bounded, and only as long as necessary

    for table in (
        "pokemon_set_cards_snapshot_latest",
        "pokemon_set_market_dashboard_snapshot_latest",
        "pokemon_set_top_chase_card_daily_history",
        "pokemon_set_page_snapshot_latest",
    ):
        assert world.published_dates(table) == {"uuid-1": "2026-07-26", "uuid-2": "2026-07-26"}, table

    # Nothing silently stuck on the previous day.
    assert "2026-07-25" not in set(world.published_dates("pokemon_set_page_snapshot_latest").values())
    assert {call["set"] for call in world.revalidations} == {"alpha", "beta"}

    freshness = world.rows[("pokemon_set_market_dashboard_snapshot_latest", "uuid-2")]["section_freshness"]
    assert freshness["referenceDate"] == "2026-07-26"
    assert freshness["marketSectionsUniformlyCurrent"] is True
    # Simulation still lags July 17 and stays explicitly stale, independently.
    assert freshness["openingProfitVsCost"]["status"] == "stale"
    assert freshness["uniformlyCurrent"] is False


def test_day_two_retry_exhaustion_still_defers_without_publishing(monkeypatch, world):
    _install(monkeypatch, world)
    world.open_cohort("2026-07-25", complete=True)
    assert _publish_day(monkeypatch, world)["exit_code"] == 0

    world.open_cohort("2026-07-26", complete=False)  # never completes
    result = _publish_day(monkeypatch, world, gate_wait_attempts=3)

    assert result["exit_code"] == 3
    assert result["waits"] == 3  # bounded — never an uncontrolled polling loop
    assert world.published_dates("pokemon_set_cards_snapshot_latest") == {
        "uuid-1": "2026-07-25",
        "uuid-2": "2026-07-25",
    }


def test_incomplete_cohort_contract_fields_each_block_publication(monkeypatch, world):
    """The real cohort contract, exercised field by field through the gate."""
    _install(monkeypatch, world)
    world.open_cohort("2026-07-26", complete=True)

    for mutation in (
        {"status": "running"},
        {"promoted_at": None},
        {"missing_set_count": 2},
        {"expected_set_count": 0},
    ):
        world.open_cohort("2026-07-26", complete=True)
        world.batch.update(mutation)
        assert _publish_day(monkeypatch, world)["exit_code"] == 3, mutation

    # And the complete contract publishes.
    world.open_cohort("2026-07-26", complete=True)
    assert _publish_day(monkeypatch, world)["exit_code"] == 0
