-- Effort 5 adversarial finding: this Collector Appeal authority retained the
-- original public USING (true) policy and broad browser-role table grants.
BEGIN;

DROP POLICY IF EXISTS pokemon_set_hit_desirability_summaries_read_policy
  ON public.pokemon_set_hit_desirability_summaries;

REVOKE ALL ON TABLE public.pokemon_set_hit_desirability_summaries
  FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.pokemon_set_hit_desirability_summaries TO service_role;

ALTER TABLE public.pokemon_set_hit_desirability_summaries ENABLE ROW LEVEL SECURITY;

COMMIT;
