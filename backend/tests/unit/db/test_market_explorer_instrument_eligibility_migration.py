from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase/migrations/20260831030409_correct_market_explorer_instrument_eligibility.sql"
VARIANT_ENGINE = ROOT / "supabase/migrations/20260829210512_market_explorer_filtered_card_cohorts.sql"
SQL = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
ENGINE_SQL = " ".join(VARIANT_ENGINE.read_text(encoding="utf-8").lower().split())


def test_physical_market_instrument_role_contract_is_fail_safe_and_explicit():
    assert "is_pokemon_market_instrument_catalog_role" in SQL
    for role in (
        "main", "subset", "pack_variant", "pack_energy", "promo",
        "promo_variant", "product_exclusive", "product_insert",
    ):
        assert f"'{role}'" in SQL
    assert "'duplicate_alias'" not in SQL
    assert "'abstract_identity'" not in SQL
    assert "coalesce(p_catalog_role = any" in SQL


def test_market_instrument_rule_does_not_use_other_product_eligibility_flags():
    assert "set_value_eligible" not in SQL
    assert "opening_eligible" not in SQL
    assert "future physical catalog roles must be explicitly reviewed and added" in SQL


def test_authority_filters_canonical_scope_before_variant_expansion():
    gate = "is_pokemon_market_instrument_catalog_role(canonical.catalog_role)"
    assert gate in SQL
    assert SQL.index(gate) < SQL.index("candidates as") < SQL.index("join public.card_variants variant")
    assert "security invoker" in SQL


def test_invalid_identity_cannot_enter_refresh_or_downstream_cohorts():
    assert "get_pokemon_canonical_card_variant_authority(scope.set_ids)" in ENGINE_SQL
    assert "join requested_variants requested" in ENGINE_SQL
    assert "pokemon_card_variant_market_price_intervals" in ENGINE_SQL
    assert "delete from public.pokemon_card_variant_market_price_intervals" in SQL


def test_cleanup_is_guarded_to_exact_celebrations_alias_scope():
    for identifier in (
        "81d1a23e-84b2-478f-a53a-195b80ee48f0",
        "974af7c8-adda-4a24-a56b-65f1a6e4bf22",
        "310b3b23-d736-46a2-bb70-0a3a7f461450",
        "aa8ab25a-5f50-4621-949f-6cfac3140da8",
    ):
        assert identifier in SQL
    assert "invalid_rows <> 116" in SQL
    assert "invalid_variants <> 2" in SQL
    assert "invalid_canonical <> 2" in SQL
    assert "invalid_sets <> 1" in SQL
    assert "raise exception" in SQL
    assert "card_variant_price_observations" not in SQL
    assert "delete from public.pokemon_canonical_cards" not in SQL


def test_authority_and_role_predicate_remain_service_only():
    for signature in (
        "public.is_pokemon_market_instrument_catalog_role(text)",
        "public.get_pokemon_canonical_card_variant_authority(uuid[])",
    ):
        assert f"revoke all on function {signature} from public, anon, authenticated" in SQL
        assert f"grant execute on function {signature} to service_role" in SQL
    assert "security definer" not in SQL
