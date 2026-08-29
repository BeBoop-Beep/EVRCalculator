-- Run as a database owner against a migrated database. Any failed assertion
-- aborts the script. Tests effective behavior, not merely catalog flags.

BEGIN;

DO $test$
DECLARE
    role_name TEXT;
    relation_name TEXT;
    can_read BOOLEAN;
    protected_relations CONSTANT TEXT[] := ARRAY[
        'pokemon_set_page_snapshot_latest',
        'pokemon_set_market_dashboard_snapshot_latest',
        'pokemon_set_sealed_market_snapshot_latest',
        'pokemon_explore_rankings_snapshot_latest',
        'pokemon_rip_stats_snapshot_latest',
        'pokemon_public_rip_leaderboard_snapshots',
        'pokemon_public_rip_leaderboard_rows',
        'explore_rip_statistics_latest',
        'set_pack_score_rankings_latest',
        'simulation_derived_metrics',
        'simulation_latest_by_target',
        'simulation_percentiles',
        'simulation_run_summary',
        'simulation_value_distribution_bins',
        'simulation_value_threshold_bins',
        'pokemon_set_opening_desirability_latest'
    ];
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        FOREACH relation_name IN ARRAY protected_relations LOOP
            IF to_regclass(format('public.%I', relation_name)) IS NULL THEN
                CONTINUE;
            END IF;

            SELECT has_table_privilege(role_name, format('public.%I', relation_name), 'SELECT')
              INTO can_read;
            IF can_read THEN
                RAISE EXCEPTION '% unexpectedly has SELECT on public.%', role_name, relation_name;
            END IF;
        END LOOP;
    END LOOP;

    FOREACH relation_name IN ARRAY protected_relations LOOP
        IF to_regclass(format('public.%I', relation_name)) IS NOT NULL
           AND NOT has_table_privilege(
               'service_role', format('public.%I', relation_name), 'SELECT'
           ) THEN
            RAISE EXCEPTION 'service_role lost SELECT on public.%', relation_name;
        END IF;
    END LOOP;

    -- Premium Chase Efficiency must remain at least as strict as before.
    FOREACH relation_name IN ARRAY ARRAY[
        'pokemon_card_chase_efficiency_latest',
        'pokemon_card_chase_efficiency_rows',
        'pokemon_card_chase_efficiency_snapshots'
    ] LOOP
        IF has_table_privilege('anon', format('public.%I', relation_name), 'SELECT')
           OR has_table_privilege('authenticated', format('public.%I', relation_name), 'SELECT')
           OR NOT has_table_privilege('service_role', format('public.%I', relation_name), 'SELECT') THEN
            RAISE EXCEPTION 'Chase Efficiency privilege regression on public.%', relation_name;
        END IF;
    END LOOP;
END
$test$;

-- Sentinel scan: no JSON-bearing analytical relation that remains reachable
-- to anon may contain a paid key. Public identity/price tables are included if
-- their relation or JSON-column name is analytical, so future additions fail
-- closed in this test.
DO $test$
DECLARE
    item RECORD;
    sentinel_found BOOLEAN;
    sentinel_pattern CONSTANT TEXT :=
        '(financialRip|financial_rip|collectorAppeal|collector_appeal|rarityContribution|rarity_contribution|marketBreadth|market_breadth|packsFor50PercentChance|packs_for_50_percent_chance|packsFor90PercentChance|packs_for_90_percent_chance|productFamilyRankings|chaseEfficiency)';
BEGIN
    FOR item IN
        SELECT c.table_schema, c.table_name, c.column_name
          FROM information_schema.columns c
         WHERE c.table_schema = 'public'
           AND c.data_type IN ('json', 'jsonb')
           AND has_table_privilege(
               'anon', format('%I.%I', c.table_schema, c.table_name), 'SELECT'
           )
           AND (
               c.table_name ~* '(analytics|rip|ranking|simulation|market|chase|economics|desirability|acquisition)'
               OR c.column_name ~* '(analytics|rip|ranking|simulation|market|chase|economics|desirability|acquisition)'
           )
    LOOP
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %I.%I WHERE %I::text ~* $1)',
            item.table_schema,
            item.table_name,
            item.column_name
        )
        INTO sentinel_found
        USING sentinel_pattern;

        IF sentinel_found THEN
            RAISE EXCEPTION 'paid sentinel reachable by anon in %.%.%',
                item.table_schema, item.table_name, item.column_name;
        END IF;
    END LOOP;
END
$test$;

ROLLBACK;
