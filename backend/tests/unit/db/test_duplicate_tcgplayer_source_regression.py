"""Regression guards for the 2026-08-22 duplicate-TCGplayer-source repair.

Batch 26 (market_date 2026-08-20) was blocked because three canonical sets failed
with ``external_variant_identity_conflict``:

  * ``base`` — Expedition was configured with TCGplayer group 604, which IS Base
    Set, so Expedition claimed all 101 group-604 identities and starved `base`.
  * ``exTrainerKit2Plusle`` / ``exTrainerKitLatios`` — both halves of each kit
    resolved to the single combined TCGplayer group (1542 / 1543).

These tests encode the invariants that must hold so a future scrape cannot
recreate today's contamination. They are deliberately config/SQL-level: they run
without a database so they gate CI on every change to the set registry.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

from backend.db.services.pokemon_set_lifecycle_flags import resolve_config_lifecycle_flags
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"
REPAIR_MIGRATION_PATH = (
    _MIGRATIONS_DIR
    / "20260822120000_repair_base_expedition_source_and_quarantine_combined_product_rosters.sql"
)

BASE_GROUP = "604"
EXPEDITION_GROUP = "1375"
TRAINER_KIT_KEYS = (
    "exTrainerKit2Plusle",
    "exTrainerKit2Minun",
    "exTrainerKitLatias",
    "exTrainerKitLatios",
)
# Combined TCGplayer groups that no single canonical child may ever claim.
COMBINED_GROUPS = {"1542", "1543"}


@pytest.fixture(scope="module")
def config_map() -> dict:
    return build_valid_set_key_registry()["config_map"]


@pytest.fixture(scope="module")
def repair_migration_sql() -> str:
    return REPAIR_MIGRATION_PATH.read_text(encoding="utf-8")


def _group_id(url: str | None) -> str | None:
    """Extract the numeric TCGplayer group id from a price-guide URL."""
    if not url:
        return None
    match = re.search(r"/priceguide/set/(\d+)/", str(url))
    return match.group(1) if match else None


def _source_groups(config_cls) -> set[str]:
    flags = resolve_config_lifecycle_flags(config_cls)
    groups = {
        _group_id(flags["card_details_url"]),
        _group_id(flags["sealed_details_url"]),
    }
    return {g for g in groups if g}


# ---------------------------------------------------------------------------
# 1. Base and Expedition cannot resolve to the same source group
# ---------------------------------------------------------------------------


def test_base_and_expedition_do_not_share_a_source_group(config_map):
    base_groups = _source_groups(config_map["base"])
    expedition_groups = _source_groups(config_map["expeditionBaseSet"])

    assert base_groups, "base must keep a TCGplayer source group"
    assert expedition_groups, "expeditionBaseSet must have a TCGplayer source group"
    assert not (base_groups & expedition_groups), (
        "base and expeditionBaseSet resolve to the same TCGplayer group "
        f"({base_groups & expedition_groups}); Expedition ingesting Base Set data "
        "is the defect that blocked batch 26"
    )


def test_base_stays_on_group_604(config_map):
    assert _source_groups(config_map["base"]) == {BASE_GROUP}


def test_expedition_uses_its_own_verified_group_1375(config_map):
    assert _source_groups(config_map["expeditionBaseSet"]) == {EXPEDITION_GROUP}


# ---------------------------------------------------------------------------
# 2/3. Printed totals — Base is a /102 set, Expedition is a /165 set
# ---------------------------------------------------------------------------


def test_base_declares_the_102_card_roster(config_map):
    base = config_map["base"]
    assert base.PRINTED_TOTAL == 102
    assert base.TOTAL == 102


def test_expedition_declares_the_165_card_roster(config_map):
    expedition = config_map["expeditionBaseSet"]
    assert expedition.PRINTED_TOTAL == 165, (
        "Expedition is a 165-card set; a /102 total means it is still modelled "
        "as Base Set"
    )
    assert expedition.TOTAL == 165


# ---------------------------------------------------------------------------
# 4/5. Combined Trainer Kit groups route deterministically — by not routing
# ---------------------------------------------------------------------------
# TCGplayer publishes ONE group per kit and its rows cannot be partitioned
# between the two canonical children (shared 1/12-12/12 numbering; only 6 of 24
# rows carry a deck marker). The deterministic, evidence-backed handling is that
# NO child claims the combined group.


@pytest.mark.parametrize("canonical_key", TRAINER_KIT_KEYS)
def test_trainer_kit_child_claims_no_combined_group(config_map, canonical_key):
    groups = _source_groups(config_map[canonical_key])
    assert not (groups & COMBINED_GROUPS), (
        f"{canonical_key} claims combined TCGplayer group {groups & COMBINED_GROUPS}; "
        "a combined product must never be attributed to one canonical half"
    )


@pytest.mark.parametrize("canonical_key", TRAINER_KIT_KEYS)
def test_trainer_kit_child_has_no_card_price_source(config_map, canonical_key):
    flags = resolve_config_lifecycle_flags(config_map[canonical_key])
    assert flags["card_details_url"] is None
    assert flags["sealed_details_url"] is None
    assert flags["has_card_details_url"] is False


@pytest.mark.parametrize("canonical_key", TRAINER_KIT_KEYS)
def test_trainer_kit_child_is_catalog_only_and_out_of_the_daily_cohort(
    config_map, canonical_key
):
    flags = resolve_config_lifecycle_flags(config_map[canonical_key])
    assert flags["catalog_only"] is True, (
        f"{canonical_key} must remain canonical but leave the publication-critical cohort"
    )
    assert flags["ready_for_daily_scrape"] is False


@pytest.mark.parametrize("canonical_key", TRAINER_KIT_KEYS)
def test_trainer_kit_child_is_still_a_canonical_set(config_map, canonical_key):
    """Removal from the cohort must not remove the set from the registry."""
    assert canonical_key in config_map


# ---------------------------------------------------------------------------
# 6. Duplicate TCGplayer group mappings are detected across the whole registry
# ---------------------------------------------------------------------------


def test_no_two_canonical_sets_share_a_tcgplayer_group(config_map):
    """The audit that would have caught this defect on day one.

    A shared group means two canonical sets ingest one product's prices — either
    one set is mis-pointed (Base/Expedition) or the product is combined and
    neither child may own it (Trainer Kits). Both are defects.
    """
    by_group: dict[str, list[str]] = defaultdict(list)
    for canonical_key, config_cls in config_map.items():
        for group in _source_groups(config_cls):
            by_group[group].append(canonical_key)

    duplicates = {
        group: sorted(keys) for group, keys in by_group.items() if len(keys) > 1
    }
    assert not duplicates, (
        f"canonical sets sharing a TCGplayer group: {duplicates}"
    )


# ---------------------------------------------------------------------------
# 7. A future scrape cannot recreate today's contamination
# ---------------------------------------------------------------------------


def test_no_config_points_at_a_combined_trainer_kit_group(config_map):
    """No set anywhere may claim 1542/1543, not just the four kit children."""
    offenders = {
        key: groups & COMBINED_GROUPS
        for key, config_cls in config_map.items()
        if (groups := _source_groups(config_cls)) & COMBINED_GROUPS
    }
    assert not offenders, f"combined TCGplayer groups claimed by: {offenders}"


def test_catalog_only_sets_are_never_daily_scrape_ready(config_map):
    """Mirrors the `sets_catalog_only_not_daily_ready` CHECK from migration 058."""
    violations = [
        key
        for key, config_cls in config_map.items()
        if (flags := resolve_config_lifecycle_flags(config_cls))["catalog_only"]
        and flags["ready_for_daily_scrape"]
    ]
    assert not violations, f"catalog-only sets marked daily-ready: {violations}"


def test_every_daily_cohort_set_has_a_card_details_url(config_map):
    """A cohort set with no card source could never satisfy completeness."""
    violations = [
        key
        for key, config_cls in config_map.items()
        if (flags := resolve_config_lifecycle_flags(config_cls))["ready_for_daily_scrape"]
        and not flags["has_card_details_url"]
    ]
    assert not violations, f"cohort sets with no card_details_url: {violations}"


# ---------------------------------------------------------------------------
# Repair migration contract
# ---------------------------------------------------------------------------


def test_repair_migration_exists():
    assert REPAIR_MIGRATION_PATH.exists()


def test_repair_migration_preserves_before_deleting(repair_migration_sql):
    """Every delete must be preceded by a quarantine insert — nothing is lost."""
    quarantine_at = repair_migration_sql.index("INSERT INTO public.canonical_repair_quarantine")
    first_delete_at = repair_migration_sql.index("DELETE FROM public.card_variant_price_observations")
    assert quarantine_at < first_delete_at, (
        "rows must be copied into quarantine before any DELETE runs"
    )


def test_repair_migration_deletes_observations_before_variants(repair_migration_sql):
    """Observations FK is ON DELETE SET NULL — wrong order orphans them."""
    obs_delete = repair_migration_sql.index("DELETE FROM public.card_variant_price_observations")
    variant_delete = repair_migration_sql.index("DELETE FROM public.card_variants")
    assert obs_delete < variant_delete, (
        "deleting variants first would orphan observations rather than remove them"
    )


def test_repair_migration_does_not_rehome_expedition_observations(repair_migration_sql):
    """The 63,393 Expedition rows are quarantined, never merged into base."""
    assert "UPDATE public.card_variant_price_observations" not in repair_migration_sql, (
        "observations must not be re-homed; 99% duplicate history base already holds"
    )


def test_repair_migration_nulls_trainer_kit_urls_explicitly(repair_migration_sql):
    """`_coalesce_value` never unsets, so the config change alone is not enough."""
    assert "card_details_url     = NULL" in repair_migration_sql
    assert "sealed_details_url   = NULL" in repair_migration_sql


def test_repair_migration_carries_the_authoritative_kit_rosters(repair_migration_sql):
    """44 cards = 12 + 12 + 10 + 10, sourced from the Pokémon TCG API."""
    roster_block = repair_migration_sql.split("INSERT INTO _kit_roster VALUES", 1)[1]
    roster_block = roster_block.split(";", 1)[0]
    for api_set, expected in (("tk1a", 10), ("tk1b", 10), ("tk2a", 12), ("tk2b", 12)):
        found = roster_block.count(f"('{api_set}',")
        assert found == expected, (
            f"{api_set} should contribute {expected} authoritative roster rows, found {found}"
        )
    assert sum(roster_block.count(f"('{s}',") for s in ("tk1a", "tk1b", "tk2a", "tk2b")) == 44


def test_repair_migration_never_leaves_a_trainer_kit_empty(repair_migration_sql):
    assert "none may be empty" in repair_migration_sql
    assert "v_kit_roster <> 44" in repair_migration_sql


def test_repair_migration_selects_kit_rosters_rather_than_inserting_cards(repair_migration_sql):
    """All 44 authoritative cards already exist; nothing may be fabricated."""
    assert "INSERT INTO public.cards" not in repair_migration_sql
    assert "INSERT INTO public.card_variants" not in repair_migration_sql


def test_repair_migration_disambiguates_kit_cards_by_deck(repair_migration_sql):
    """Bare name+number is ambiguous: Potion (Latias) vs Potion (Latios) at 8/10."""
    assert "_kit_deck" in repair_migration_sql
    assert "deck_name" in repair_migration_sql


def test_repair_migration_asserts_its_invariants(repair_migration_sql):
    for invariant in (
        "contaminated /102 Expedition cards remain",
        "Trainer Kit TCGplayer URLs still active",
        "Trainer Kit external identities still attached",
        "expected a 163-set daily cohort",
        "canonical set count changed",
        "orphan observations",
        "base observations changed",
    ):
        assert invariant in repair_migration_sql, f"missing postcondition: {invariant}"
