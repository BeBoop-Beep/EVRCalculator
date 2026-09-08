DO $do$
DECLARE
  v_def text;
BEGIN
  SELECT pg_get_functiondef(p.oid)
    INTO v_def
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='get_pokemon_market_root_set_card_prices_latest_v1'
    AND p.prokind='f'
  LIMIT 1;

  IF v_def IS NULL THEN
    RAISE EXCEPTION 'Root-set latest-price function not found';
  END IF;

  v_def := replace(v_def,
    'CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1(',
    'CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(');
  v_def := replace(v_def,
    'FROM public.card_variant_price_observations o',
    'FROM public.card_variant_price_current_v2 o');
  v_def := replace(v_def,
    'SELECT o.market_price, o.captured_at, o.source',
    'SELECT o.market_price, o.last_observed_date AS captured_at, o.source');
  v_def := replace(v_def,
    'ORDER BY o.captured_at DESC NULLS LAST, o.created_at DESC NULLS LAST, o.id DESC',
    'ORDER BY o.last_observed_date DESC NULLS LAST, o.last_observation_created_at DESC NULLS LAST, o.last_observation_id DESC');

  EXECUTE v_def;
END
$do$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(uuid) TO service_role;