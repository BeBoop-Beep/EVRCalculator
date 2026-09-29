BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE public.pkmnprices_sold_condition_classifications_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sold_evidence_id uuid NOT NULL REFERENCES public.pkmnprices_ebay_sold_evidence_v1(id) ON DELETE RESTRICT,
  classifier_version text NOT NULL CHECK (btrim(classifier_version) <> ''),
  condition_label text NOT NULL CHECK (condition_label IN ('NM','LP','MP','HP','DAMAGED','AMBIGUOUS','UNLABELED')),
  confidence text NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW','NONE')),
  evidence_tokens jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence_tokens) = 'array'),
  ambiguity_reason text,
  classified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (sold_evidence_id, classifier_version),
  CHECK ((condition_label = 'AMBIGUOUS') = (ambiguity_reason IS NOT NULL)),
  CHECK (condition_label <> 'UNLABELED' OR jsonb_array_length(evidence_tokens) = 0)
);

COMMENT ON TABLE public.pkmnprices_sold_condition_classifications_v1 IS
  'Versioned research-only title classification. Does not mutate sold evidence and is not a condition-price adjustment or pricing authority.';

ALTER TABLE public.pkmnprices_sold_condition_classifications_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pkmnprices_sold_condition_classifications_v1 FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.pkmnprices_sold_condition_classifications_v1 TO service_role;

COMMIT;
