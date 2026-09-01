-- Atomic, service-only reliability primitives for Stripe synchronization.
-- Browser roles remain unable to read or mutate billing state.

create or replace function public.claim_billing_webhook_event(
  p_provider_event_id text,
  p_event_type text,
  p_stale_before timestamptz
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  claimed_id uuid;
  existing_status text;
begin
  insert into public.billing_webhook_events (
    provider, provider_event_id, event_type, processing_status,
    processing_attempts, processing_started_at, updated_at
  ) values (
    'stripe', p_provider_event_id, p_event_type, 'processing', 1, now(), now()
  )
  on conflict (provider, provider_event_id) do update
    set processing_status = 'processing',
        processing_attempts = public.billing_webhook_events.processing_attempts + 1,
        processing_started_at = now(),
        updated_at = now(),
        error_code = null,
        error_summary = null
    where public.billing_webhook_events.processing_status = 'failed'
       or (
         public.billing_webhook_events.processing_status in ('received', 'processing')
         and coalesce(public.billing_webhook_events.processing_started_at, '-infinity'::timestamptz) < p_stale_before
       )
  returning id into claimed_id;

  if claimed_id is not null then
    return 'claimed';
  end if;

  select processing_status into existing_status
  from public.billing_webhook_events
  where provider = 'stripe' and provider_event_id = p_provider_event_id;
  return case when existing_status = 'processed' then 'duplicate' else 'busy' end;
end;
$$;

create or replace function public.persist_billing_subscription_and_recompute(p_subscription jsonb)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  persisted public.billing_subscriptions;
begin
  insert into public.billing_subscriptions (
    user_id, billing_customer_id, provider, provider_subscription_id,
    provider_product_id, provider_price_id, offer_key, plan, status,
    current_period_start, current_period_end, cancel_at_period_end,
    canceled_at, ended_at, commercial_mapping_status, last_reconciled_at,
    reconciliation_error_code
  ) values (
    (p_subscription->>'user_id')::uuid,
    (p_subscription->>'billing_customer_id')::uuid,
    'stripe',
    p_subscription->>'provider_subscription_id',
    p_subscription->>'provider_product_id',
    p_subscription->>'provider_price_id',
    p_subscription->>'offer_key',
    p_subscription->>'plan',
    coalesce(p_subscription->>'status', 'unknown'),
    (p_subscription->>'current_period_start')::timestamptz,
    (p_subscription->>'current_period_end')::timestamptz,
    coalesce((p_subscription->>'cancel_at_period_end')::boolean, false),
    (p_subscription->>'canceled_at')::timestamptz,
    (p_subscription->>'ended_at')::timestamptz,
    coalesce(p_subscription->>'commercial_mapping_status', 'unsupported_shape'),
    coalesce((p_subscription->>'last_reconciled_at')::timestamptz, now()),
    p_subscription->>'reconciliation_error_code'
  )
  on conflict (provider, provider_subscription_id) do update set
    user_id = excluded.user_id,
    billing_customer_id = excluded.billing_customer_id,
    provider_product_id = excluded.provider_product_id,
    provider_price_id = excluded.provider_price_id,
    offer_key = excluded.offer_key,
    plan = excluded.plan,
    status = excluded.status,
    current_period_start = excluded.current_period_start,
    current_period_end = excluded.current_period_end,
    cancel_at_period_end = excluded.cancel_at_period_end,
    canceled_at = excluded.canceled_at,
    ended_at = excluded.ended_at,
    commercial_mapping_status = excluded.commercial_mapping_status,
    last_reconciled_at = excluded.last_reconciled_at,
    reconciliation_error_code = excluded.reconciliation_error_code,
    updated_at = now()
  returning * into persisted;

  perform public.recompute_effective_index_plan(persisted.user_id);
  return to_jsonb(persisted);
end;
$$;

create or replace function public.mark_missing_billing_subscriptions_and_recompute(
  p_user_id uuid,
  p_current_provider_subscription_ids text[]
)
returns integer
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare affected integer;
begin
  update public.billing_subscriptions
  set status = 'canceled',
      reconciliation_error_code = 'LOCAL_SUBSCRIPTION_STALE',
      last_reconciled_at = now(),
      updated_at = now()
  where user_id = p_user_id
    and provider = 'stripe'
    and not (provider_subscription_id = any(coalesce(p_current_provider_subscription_ids, array[]::text[])))
    and status <> 'canceled';
  get diagnostics affected = row_count;
  perform public.recompute_effective_index_plan(p_user_id);
  return affected;
end;
$$;

revoke all on function public.claim_billing_webhook_event(text, text, timestamptz) from public, anon, authenticated;
revoke all on function public.persist_billing_subscription_and_recompute(jsonb) from public, anon, authenticated;
revoke all on function public.mark_missing_billing_subscriptions_and_recompute(uuid, text[]) from public, anon, authenticated;
grant execute on function public.claim_billing_webhook_event(text, text, timestamptz) to service_role;
grant execute on function public.persist_billing_subscription_and_recompute(jsonb) to service_role;
grant execute on function public.mark_missing_billing_subscriptions_and_recompute(uuid, text[]) to service_role;

create index if not exists billing_webhook_events_failed_updated_idx
  on public.billing_webhook_events (processing_status, updated_at)
  where processing_status in ('processing', 'failed');
create index if not exists billing_subscriptions_customer_status_idx
  on public.billing_subscriptions (billing_customer_id, status);
