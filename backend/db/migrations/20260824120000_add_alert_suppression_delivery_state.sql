-- Preserve historical alert_events while explicitly removing them from delivery.
ALTER TABLE public.alert_events
  ADD COLUMN IF NOT EXISTS dedupe_key text,
  ADD COLUMN IF NOT EXISTS suppressed_at timestamptz,
  ADD COLUMN IF NOT EXISTS suppression_reason text;

-- Deliberately non-unique on rollout: historical rows may already contain
-- duplicate keys. Application-level idempotency prevents new duplicates without
-- making this safety migration fail or silently suppressing old incident rows.
CREATE INDEX IF NOT EXISTS alert_events_dedupe_key_idx
  ON public.alert_events (dedupe_key) WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS alert_events_pending_delivery_idx
  ON public.alert_events (created_at)
  WHERE sent = false AND suppressed_at IS NULL;

COMMENT ON COLUMN public.alert_events.suppressed_at IS
  'Explicit operator suppression time; suppressed rows remain incident history and are never dispatched.';
COMMENT ON COLUMN public.alert_events.suppression_reason IS
  'Operator-provided reason for suppressing delivery without deleting the alert.';
