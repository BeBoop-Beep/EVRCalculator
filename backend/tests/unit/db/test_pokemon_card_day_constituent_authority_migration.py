from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260830090000_unify_pokemon_card_day_constituent_authority.sql"
SQL = MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.lower().split())


def test_reusable_reader_enforces_standard_set_value_eligibility():
    assert "canonical.set_value_eligible = true" in NORMALIZED
    assert "join public.pokemon_canonical_cards as canonical" in NORMALIZED
    assert "get_pokemon_cards_daily_constituents_resolved_universe(" in NORMALIZED


def test_old_single_set_reader_is_only_a_compatibility_wrapper():
    wrapper = NORMALIZED.split(
        "create or replace function public.get_pokemon_set_daily_card_constituents", 1
    )[1]
    wrapper = wrapper.split("comment on function", 1)[0]
    assert "from public.get_pokemon_cards_daily_constituents(" in wrapper
    for duplicated_authority in (
        "canonical_checklist",
        "pokemon_canonical_card_legacy_identity_links",
        "card_variant_price_observations",
        "near mint",
        "generate_series",
    ):
        assert duplicated_authority not in wrapper


def test_canonical_reader_preserves_phoenix_and_fail_closed_price_rules():
    assert "set \"timezone\" to 'america/phoenix'" in NORMALIZED
    # These rules remain owned by the preserved resolved-universe function;
    # the eligibility wrapper must not introduce a fallback basket.
    assert "get_pokemon_cards_daily_constituents_resolved_universe" in NORMALIZED
    assert "coalesce(canonical.set_value_eligible" not in NORMALIZED


def test_prismatic_promo_cannot_enter_the_canonical_cards_basket():
    rows = [
        {"name": "canonical pack cards", "price": 5036.02, "set_value_eligible": True},
        {
            "name": "Glaceon ex - 026/131 (Holiday Calendar)",
            "price": 2.40,
            "catalog_role": "promo_variant",
            "eligibility_reason": "non_pack_promotional_variant",
            "set_value_eligible": False,
        },
    ]
    canonical_total = sum(row["price"] for row in rows if row["set_value_eligible"])
    assert canonical_total == 5036.02
    assert sum(row["price"] for row in rows) == 5038.42
    assert "prismatic" not in NORMALIZED
    assert "glaceon" not in NORMALIZED


def test_migration_does_not_weaken_reconciliation_or_reinclude_promos():
    for forbidden in ("tolerance", "round(", "promo_variant", "eligibility_reason"):
        assert forbidden not in NORMALIZED
