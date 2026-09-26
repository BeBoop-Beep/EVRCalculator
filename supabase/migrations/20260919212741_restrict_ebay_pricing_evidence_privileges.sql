begin;

revoke all on public.ebay_pricing_runs_v1, public.ebay_card_listing_evidence_v1,
  public.ebay_card_pricing_run_summary_v1 from public, anon, authenticated, service_role;
grant select, insert, update on public.ebay_pricing_runs_v1, public.ebay_card_listing_evidence_v1,
  public.ebay_card_pricing_run_summary_v1 to service_role;

commit;
