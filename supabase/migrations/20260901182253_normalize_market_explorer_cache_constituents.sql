BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_explorer_query_cache_constituents (
  query_fingerprint text NOT NULL REFERENCES public.pokemon_market_explorer_query_cache(query_fingerprint) ON DELETE CASCADE,
  rank integer NOT NULL CHECK (rank > 0),
  card_variant_id uuid,
  item jsonb NOT NULL,
  PRIMARY KEY (query_fingerprint,rank)
);
ALTER TABLE public.pokemon_market_explorer_query_cache_constituents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_explorer_query_cache_constituents FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_market_explorer_query_cache_constituents TO service_role;

CREATE OR REPLACE FUNCTION public.sync_pokemon_market_explorer_query_cache_constituents()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=''
AS $function$
BEGIN
  DELETE FROM public.pokemon_market_explorer_query_cache_constituents
  WHERE query_fingerprint=NEW.query_fingerprint;
  INSERT INTO public.pokemon_market_explorer_query_cache_constituents(
    query_fingerprint,rank,card_variant_id,item
  )
  SELECT NEW.query_fingerprint,ordinality::integer,
         nullif(value->>'cardVariantId','')::uuid,value
  FROM jsonb_array_elements(coalesce(NEW.current_constituents,'[]'::jsonb)) WITH ORDINALITY;
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS trg_sync_market_explorer_query_cache_constituents
ON public.pokemon_market_explorer_query_cache;
CREATE TRIGGER trg_sync_market_explorer_query_cache_constituents
AFTER INSERT OR UPDATE OF current_constituents
ON public.pokemon_market_explorer_query_cache
FOR EACH ROW EXECUTE FUNCTION public.sync_pokemon_market_explorer_query_cache_constituents();

INSERT INTO public.pokemon_market_explorer_query_cache_constituents(
  query_fingerprint,rank,card_variant_id,item
)
SELECT c.query_fingerprint,x.ordinality::integer,
       nullif(x.value->>'cardVariantId','')::uuid,x.value
FROM public.pokemon_market_explorer_query_cache c
CROSS JOIN LATERAL jsonb_array_elements(coalesce(c.current_constituents,'[]'::jsonb))
  WITH ORDINALITY x(value,ordinality)
ON CONFLICT (query_fingerprint,rank) DO UPDATE
SET card_variant_id=excluded.card_variant_id,item=excluded.item;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_query_cache_constituent_page(
  p_query_fingerprint text,p_limit integer DEFAULT 100,p_after_rank integer DEFAULT 0
) RETURNS TABLE(items jsonb,next_cursor integer,total_constituent_count bigint,as_of date)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=''
AS $function$
  WITH page AS MATERIALIZED (
    SELECT d.rank,d.item
    FROM public.pokemon_market_explorer_query_cache_constituents d
    WHERE d.query_fingerprint=p_query_fingerprint
      AND d.rank>greatest(p_after_rank,0)
    ORDER BY d.rank LIMIT least(greatest(p_limit,1),100)
  ), totals AS MATERIALIZED (
    SELECT count(*)::bigint total,c.computed_through
    FROM public.pokemon_market_explorer_query_cache_constituents d
    JOIN public.pokemon_market_explorer_query_cache c USING(query_fingerprint)
    WHERE d.query_fingerprint=p_query_fingerprint AND c.status='ready'
    GROUP BY c.computed_through
  )
  SELECT coalesce(jsonb_agg(p.item ORDER BY p.rank),'[]'::jsonb),
         CASE WHEN max(p.rank)<t.total THEN max(p.rank) END,t.total,t.computed_through
  FROM totals t LEFT JOIN page p ON true GROUP BY t.total,t.computed_through
$function$;

COMMIT;
