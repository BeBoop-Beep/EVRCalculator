from pathlib import Path


SQL = (Path(__file__).resolve().parents[4] / "supabase" / "migrations" /
       "20260829210512_market_explorer_filtered_card_cohorts.sql").read_text(encoding="utf-8")
ACL_SQL = (Path(__file__).resolve().parents[4] / "supabase" / "migrations" /
           "20260830190812_harden_market_explorer_variant_interval_acl.sql").read_text(encoding="utf-8")


def test_variant_interval_acl_chain_revokes_defaults_before_least_privilege_grant():
    normalized = " ".join(ACL_SQL.lower().split())
    table = "public.pokemon_card_variant_market_price_intervals"
    revoke = (
        f"revoke all privileges on table {table} "
        "from public, anon, authenticated, service_role;"
    )
    grant = f"grant select, insert, delete on table {table} to service_role;"

    assert revoke in normalized
    assert grant in normalized
    assert normalized.index(revoke) < normalized.index(grant)
    for privilege in ("update", "truncate", "references", "trigger"):
        assert f"grant {privilege}" not in normalized


def test_filtered_cohort_rpc_is_service_only_and_invoker_safe():
    normalized = " ".join(SQL.lower().split())
    assert "security invoker" in normalized
    assert "revoke all on function" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "grant execute on function" in normalized
    assert "to service_role" in normalized
    assert "security definer" not in normalized


def test_filter_first_rank_second_and_point_in_time_authorities_are_in_sql():
    assert SQL.index("panel AS MATERIALIZED") < SQL.index("ranked AS") < SQL.index("selected AS MATERIALIZED")
    assert "fact.market_price<10" in SQL
    assert "fact.market_price>=100" in SQL
    assert "dates.market_date-set_row.release_date" in SQL
    assert "PARTITION BY market_date" in SQL
    assert "ORDER BY market_price DESC, card_variant_id" in SQL
    assert "prev.card_variant_id=cur.card_variant_id" in SQL


def test_rpc_returns_reduced_dates_and_only_latest_constituent_identity():
    assert "current_constituents jsonb" in SQL
    assert "dates.market_date=dates.latest_market_date" in SQL
    assert "eligible_universe_count" in SQL
    assert "common_previous_value" in SQL


def test_variant_interval_authority_is_near_mint_usd_and_not_condition_exploded():
    normalized = " ".join(SQL.lower().split())
    assert "pokemon_card_variant_market_price_intervals" in normalized
    assert "lower(name) = 'near mint'" in normalized
    assert "upper(abbreviation) = 'nm'" in normalized
    assert "partition by authority.card_variant_id, observation.captured_at" in normalized
    assert "partition by card_variant_id order by source_date" in normalized
    assert "card_variant_id is the traded instrument" in normalized


def test_schema_migration_never_launches_a_global_historical_refresh():
    executable = "\n".join(
        line for line in SQL.splitlines() if not line.lstrip().startswith("--")
    )
    assert "SELECT public.refresh_pokemon_card_variant_market_price_intervals(NULL" not in executable
    assert "Historical population is intentionally NOT part of this migration" in SQL


def test_variant_refresh_is_bounded_noop_safe_and_variant_partitioned():
    normalized = " ".join(SQL.lower().split())
    assert "if p_card_variant_ids is null or cardinality(p_card_variant_ids) = 0 then return 0" in normalized
    assert "interval_row.card_variant_id = any(p_card_variant_ids)" in normalized
    assert "delete from public.pokemon_card_variant_market_price_intervals" in normalized
    assert "join requested_variants requested on requested.card_variant_id = authority.card_variant_id" in normalized
    assert "partition by authority.card_variant_id, observation.captured_at" in normalized
    assert "partition by card_variant_id order by source_date" in normalized
    assert "observation.condition_id = v_nm" in normalized
    assert "observation.market_price > 0" in normalized
    assert "upper(coalesce(observation.currency, ''))" in normalized
    assert "= 'usd'" in normalized


def test_set_refresh_has_a_distinct_backend_only_rpc_name():
    normalized = " ".join(SQL.lower().split())
    name = "refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[])"
    assert name in normalized
    assert f"revoke all on function public.{name} from public, anon, authenticated" in normalized
    assert f"grant execute on function public.{name} to service_role" in normalized


def test_canonical_to_variant_authority_prefers_verified_identity_paths():
    normalized = " ".join(SQL.lower().split())
    explicit = normalized.index("explicit_legacy_identity_link")
    parent_api = normalized.index("parent_pokemon_tcg_api_id")
    variant_api = normalized.index("variant_pokemon_tcg_api_id")
    fallback = normalized.index("normalized_name_number_fallback")
    assert explicit < parent_api < variant_api < fallback
    assert "order by canonical_card_id, identity_rank, legacy_card_id" in normalized


def test_rarity_and_pokemon_intersections_execute_inside_the_rpc():
    normalized = " ".join(SQL.lower().split())
    assert "p_segment_ids text[]" in normalized
    assert "p_pokemon_ids bigint[]" in normalized
    assert "market_explorer_rarity_segment(fact.rarity)=any(p_segment_ids)" in normalized
    assert "pokemon_card_desirability_links pokemon_link" in normalized
    assert "pokemon_link.pokemon_canonical_card_id=fact.canonical_card_id" in normalized
