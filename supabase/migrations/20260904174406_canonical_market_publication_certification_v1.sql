BEGIN;

CREATE OR REPLACE VIEW public.pokemon_market_root_set_publication_certification_v1
WITH (security_invoker = true)
AS
WITH top_counts AS (
    SELECT set_id,
           market_scope,
           count(*)::integer AS top10_row_count,
           max(rank)::integer AS max_rank
    FROM public.pokemon_market_root_set_top10_latest_v1
    GROUP BY set_id, market_scope
)
SELECT value.set_id,
       value.set_name,
       value.market_scope,
       value.set_value,
       value.expected_card_count,
       value.resolved_variant_count,
       value.priced_card_count,
       value.coverage_pct,
       value.oldest_component_price_date,
       value.newest_component_price_date,
       value.needs_review_card_count,
       value.missing_required_variant_count,
       value.missing_price_count,
       value.quality_status,
       value.publishable_100pct AS set_value_certified,
       least(10, value.expected_card_count)::integer AS expected_top10_rows,
       coalesce(top.top10_row_count, 0)::integer AS top10_row_count,
       coalesce(top.max_rank, 0)::integer AS top10_max_rank,
       (
          value.publishable_100pct
          AND coalesce(top.top10_row_count, 0) = least(10, value.expected_card_count)
          AND coalesce(top.max_rank, 0) = least(10, value.expected_card_count)
       ) AS top10_certified,
       (
          value.publishable_100pct
          AND coalesce(top.top10_row_count, 0) = least(10, value.expected_card_count)
          AND coalesce(top.max_rank, 0) = least(10, value.expected_card_count)
       ) AS market_scope_certified,
       CASE
         WHEN value.expected_card_count = 0 THEN 'NO_ELIGIBLE_CARDS'
         WHEN value.needs_review_card_count > 0 THEN 'CANONICAL_IDENTITY_REVIEW_REQUIRED'
         WHEN value.missing_required_variant_count > 0 THEN 'REQUIRED_VARIANT_IDENTITY_MISSING'
         WHEN value.resolved_variant_count < value.expected_card_count THEN 'CANONICAL_PRICE_IDENTITY_MISSING'
         WHEN value.missing_price_count > 0 OR value.priced_card_count < value.expected_card_count THEN 'NEAR_MINT_USD_PRICE_MISSING'
         WHEN coalesce(top.top10_row_count, 0) <> least(10, value.expected_card_count) THEN 'TOP10_ROW_COUNT_MISMATCH'
         WHEN coalesce(top.max_rank, 0) <> least(10, value.expected_card_count) THEN 'TOP10_RANK_SEQUENCE_MISMATCH'
         ELSE 'CERTIFIED'
       END AS certification_status
FROM public.pokemon_market_root_set_value_latest_v1 value
LEFT JOIN top_counts top
  ON top.set_id = value.set_id
 AND top.market_scope = value.market_scope;

COMMENT ON VIEW public.pokemon_market_root_set_publication_certification_v1 IS
'Fail-closed certification for current Set Value and Top 10. A scope is certified only when every eligible canonical card resolves to the required physical variant scope, every card has a positive Near Mint USD price, and the Top 10 is a complete 1..min(10,N) ranking from those exact same constituents.';

REVOKE ALL ON public.pokemon_market_root_set_publication_certification_v1 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_market_root_set_publication_certification_v1 TO service_role;

COMMIT;
