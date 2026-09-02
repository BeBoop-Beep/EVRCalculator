BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_query_cache_summary(
  p_query_fingerprint text
) RETURNS TABLE(
  query_fingerprint text,status text,computed_from date,computed_through date,
  series_payload jsonb,build_token uuid,build_expires_at timestamptz
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
  SELECT c.query_fingerprint,c.status,c.computed_from,c.computed_through,
         c.series_payload - 'currentConstituents' - 'membershipByDate',
         c.build_token,c.build_expires_at
  FROM public.pokemon_market_explorer_query_cache c
  WHERE c.query_fingerprint=p_query_fingerprint
  LIMIT 1
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_query_cache_constituent_page(
  p_query_fingerprint text,p_limit integer DEFAULT 100,p_after_rank integer DEFAULT 0
) RETURNS TABLE(items jsonb,next_cursor integer,total_constituent_count bigint,as_of date)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
  WITH target AS MATERIALIZED (
    SELECT c.current_constituents,c.computed_through
    FROM public.pokemon_market_explorer_query_cache c
    WHERE c.query_fingerprint=p_query_fingerprint AND c.status='ready'
  ), expanded AS MATERIALIZED (
    SELECT value item,ordinality::integer rank
    FROM target,jsonb_array_elements(target.current_constituents) WITH ORDINALITY
    WHERE ordinality>greatest(p_after_rank,0)
    ORDER BY ordinality LIMIT least(greatest(p_limit,1),100)
  )
  SELECT coalesce(jsonb_agg(item ORDER BY rank) FILTER (WHERE item IS NOT NULL),'[]'::jsonb),
         CASE WHEN max(rank)<jsonb_array_length(t.current_constituents) THEN max(rank) END,
         jsonb_array_length(t.current_constituents)::bigint,t.computed_through
  FROM target t LEFT JOIN expanded e ON true
  GROUP BY t.current_constituents,t.computed_through
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_query_cache_summary(text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_query_cache_constituent_page(text,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_query_cache_summary(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_query_cache_constituent_page(text,integer,integer) TO service_role;

COMMIT;
