begin;
set local lock_timeout = '5s';

-- P4C estimates are append-only, finalized evidence: the estimator writer only ever SELECTs and INSERTs, and the
-- unique (variant, condition, market_date, estimator_version) key makes changed replays fail closed. Supabase default
-- privileges had granted service_role UPDATE, DELETE and TRUNCATE (and REFERENCES/TRIGGER), contradicting that intent.
-- No correction workflow exists or is needed: a corrected estimate is a new estimator_version row, never a mutation.
revoke all on public.ebay_active_ask_price_estimates_v1 from public, anon, authenticated, service_role;
grant select, insert on public.ebay_active_ask_price_estimates_v1 to service_role;

commit;
