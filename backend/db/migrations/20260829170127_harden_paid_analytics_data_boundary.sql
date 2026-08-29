-- Make proprietary analytical authority backend-only.
--
-- Public pages must consume the backend's explicit Base projections.  The
-- relations below are canonical/raw inputs and deliberately have no direct
-- anon or ordinary-authenticated Data API read path.

BEGIN;

DO $migration$
DECLARE
    relation_name TEXT;
    policy_name TEXT;
    relation_kind "char";
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        -- Canonical snapshot payloads (contain mixed Base/Plus/Premium data).
        'pokemon_set_page_snapshot_latest',
        'pokemon_set_market_dashboard_snapshot_latest',
        'pokemon_explore_rankings_snapshot_latest',
        'pokemon_rip_stats_snapshot_latest',
        'pokemon_public_rip_leaderboard_snapshots',
        'pokemon_public_rip_leaderboard_rows',

        -- Raw simulation/RIP authority and its detailed read models.
        'calculation_runs',
        'simulation_card_variant_exclusions',
        'simulation_derived_metrics',
        'simulation_etb_summary',
        'simulation_input_cards',
        'simulation_input_cards_with_near_mint_price',
        'simulation_latest_by_target',
        'simulation_latest_by_target__base',
        'simulation_percentiles',
        'simulation_pull_summary',
        'simulation_run_summary',
        'simulation_state_counts',
        'simulation_value_distribution_bins',
        'simulation_value_threshold_bins',
        'explore_rip_distribution_latest',
        'explore_rip_percentiles_latest',
        'explore_rip_statistics_latest',
        'explore_rip_statistics_latest__base',
        'explore_rip_threshold_distribution_latest',
        'set_pack_score_rankings_latest',
        'set_pack_score_rankings_latest__base',
        'set_pack_score_rankings_latest__tier_base',

        -- Detailed Collector Appeal / desirability analytical authority.
        'pokemon_set_desirability_component_scores',
        'pokemon_set_opening_desirability_scores',
        'pokemon_set_opening_desirability_latest',
        'pokemon_desirability_composite_scores',
        'pokemon_desirability_scores',
        'pokemon_desirability_source_rows',
        'pokemon_desirability_source_snapshots',
        'pokemon_desirability_validation_snapshot_latest',
        'pokemon_trend_scores',
        'pokemon_trend_source_rows',
        'pokemon_trend_source_snapshots'
    ] LOOP
        SELECT c.relkind
          INTO relation_kind
          FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname = relation_name
           AND c.relkind IN ('r', 'p', 'v', 'm');

        IF NOT FOUND THEN
            CONTINUE;
        END IF;

        -- Remove every SELECT policy, including policies granted to PUBLIC.
        IF relation_kind IN ('r', 'p') THEN
            FOR policy_name IN
                SELECT p.policyname
                  FROM pg_catalog.pg_policies p
                 WHERE p.schemaname = 'public'
                   AND p.tablename = relation_name
                   AND p.cmd IN ('SELECT', 'ALL')
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS %I ON public.%I',
                    policy_name,
                    relation_name
                );
            END LOOP;

            EXECUTE format(
                'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                relation_name
            );
        END IF;

        EXECUTE format(
            'REVOKE SELECT ON public.%I FROM PUBLIC, anon, authenticated',
            relation_name
        );
        EXECUTE format(
            'GRANT SELECT ON public.%I TO service_role',
            relation_name
        );
    END LOOP;
END
$migration$;

-- These mutation/refresh RPCs are operational jobs, not browser APIs.  They
-- are SECURITY INVOKER today, but PostgreSQL grants EXECUTE to PUBLIC by
-- default; remove that unnecessary callable surface explicitly.
DO $migration$
DECLARE
    function_signature REGPROCEDURE;
BEGIN
    FOREACH function_signature IN ARRAY ARRAY[
        to_regprocedure('public.refresh_card_market_top_hits_by_edition_latest()'),
        to_regprocedure('public.refresh_card_market_top_hits_latest()'),
        to_regprocedure('public.refresh_card_variant_market_metrics_latest()'),
        to_regprocedure('public.refresh_market_analytics_latest()'),
        to_regprocedure('public.refresh_set_market_metrics_by_edition_latest()'),
        to_regprocedure('public.refresh_set_market_metrics_latest()'),
        to_regprocedure('public.refresh_set_market_snapshot_wrapper()'),
        to_regprocedure('public.snapshot_set_market_metrics_by_edition_latest()'),
        to_regprocedure('public.snapshot_set_market_metrics_latest()')
    ] LOOP
        IF function_signature IS NULL THEN
            CONTINUE;
        END IF;

        EXECUTE format(
            'REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon, authenticated',
            function_signature
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION %s TO service_role',
            function_signature
        );
    END LOOP;
END
$migration$;

COMMIT;


