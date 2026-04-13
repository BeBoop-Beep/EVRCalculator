ALTER TABLE public.card_variants
ADD COLUMN IF NOT EXISTS pokemon_tcg_api_id text,
ADD COLUMN IF NOT EXISTS image_small_url text,
ADD COLUMN IF NOT EXISTS image_large_url text,
ADD COLUMN IF NOT EXISTS image_last_synced_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_card_variants_pokemon_tcg_api_id
ON public.card_variants (pokemon_tcg_api_id);