CREATE TABLE IF NOT EXISTS public.pokemon_market_root_authority (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  set_id uuid NOT NULL,
  activated_market_date date NOT NULL,
  deactivated_market_date date NULL,
  enabled boolean NOT NULL DEFAULT true,
  source text NOT NULL,
  notes text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pokemon_market_root_authority_range_chk CHECK (deactivated_market_date IS NULL OR deactivated_market_date > activated_market_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS pokemon_market_root_authority_set_activation_uq
  ON public.pokemon_market_root_authority (set_id, activated_market_date);
CREATE INDEX IF NOT EXISTS pokemon_market_root_authority_lookup_idx
  ON public.pokemon_market_root_authority (set_id, activated_market_date, deactivated_market_date) WHERE enabled;
CREATE INDEX IF NOT EXISTS pokemon_market_root_authority_enabled_activated_idx
  ON public.pokemon_market_root_authority (activated_market_date) WHERE enabled;

CREATE OR REPLACE FUNCTION public.set_pokemon_market_root_authority_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS pokemon_market_root_authority_touch_updated_at ON public.pokemon_market_root_authority;
CREATE TRIGGER pokemon_market_root_authority_touch_updated_at
BEFORE UPDATE ON public.pokemon_market_root_authority
FOR EACH ROW EXECUTE FUNCTION public.set_pokemon_market_root_authority_updated_at();

DO $$
DECLARE
  v_count bigint;
  v_fp text;
BEGIN
  SELECT count(*), encode(digest(replace(json_agg(set_id::text order by set_id::text)::text, ', ', ','), 'sha256'),'hex')
  INTO v_count, v_fp
  FROM public.pokemon_market_set_value_publication_cohort_v1
  WHERE market_scope='standard';

  IF v_count <> 106 OR v_fp <> '470c8e49e083ca29c7df4d075175b62fb5dd69311b67ca48fec6baf76cd6e892' THEN
    RAISE EXCEPTION 'authority source mismatch: count=%, fingerprint=%', v_count, v_fp;
  END IF;

  INSERT INTO public.pokemon_market_root_authority(set_id, activated_market_date, enabled, source, notes)
  SELECT set_id, DATE '2026-09-10', true,
         'verified_snapshot_pokemon_market_set_value_publication_cohort_v1_2026-09-12',
         'Frozen Sep-10 authority seeded only after exact 106-root fingerprint verification.'
  FROM public.pokemon_market_set_value_publication_cohort_v1
  WHERE market_scope='standard'
  ON CONFLICT (set_id, activated_market_date) DO NOTHING;
END
$$;

ALTER TABLE public.pokemon_market_root_authority ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_root_authority FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.pokemon_market_root_authority TO service_role;
REVOKE ALL ON SEQUENCE public.pokemon_market_root_authority_id_seq FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.set_pokemon_market_root_authority_updated_at() FROM PUBLIC, anon, authenticated, service_role;

