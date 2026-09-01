-- Forward-only Stripe synchronization support. Browser roles remain denied.
alter table public.billing_subscriptions alter column offer_key drop not null;
alter table public.billing_subscriptions alter column plan drop not null;
alter table public.billing_subscriptions
  add column commercial_mapping_status text not null default 'mapped'
    check (commercial_mapping_status in ('mapped', 'unmapped_price', 'unsupported_shape')),
  add column last_reconciled_at timestamptz,
  add column reconciliation_error_code text;

alter table public.billing_webhook_events
  add column processing_attempts integer not null default 0,
  add column processing_started_at timestamptz,
  add column updated_at timestamptz not null default now();

create table public.billing_manual_entitlements (
  user_id uuid primary key references public.users(id) on delete cascade,
  plan text not null check (plan in ('plus', 'premium')),
  reason text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.billing_manual_entitlements enable row level security;
revoke all on public.billing_manual_entitlements from anon, authenticated;
grant select, insert, update, delete on public.billing_customers to service_role;
grant select, insert, update, delete on public.billing_subscriptions to service_role;
grant select, insert, update, delete on public.billing_webhook_events to service_role;
grant select, insert, update, delete on public.billing_manual_entitlements to service_role;

-- Preserve every pre-Stripe paid value as an explicit manual entitlement.
-- This migration does not silently claim those accounts are Stripe-managed.
insert into public.billing_manual_entitlements (user_id, plan, reason)
select id, index_plan, 'pre_stripe_entitlement_migration'
from public.users where index_plan in ('plus', 'premium')
on conflict (user_id) do nothing;

create or replace function public.recompute_effective_index_plan(target_user_id uuid)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare resolved_plan text;
begin
  select case
    when bool_or(candidate_plan = 'premium') then 'premium'
    when bool_or(candidate_plan = 'plus') then 'plus'
    else null
  end into resolved_plan
  from (
    select plan as candidate_plan from public.billing_manual_entitlements where user_id = target_user_id
    union all
    select plan from public.billing_subscriptions
    where user_id = target_user_id
      and commercial_mapping_status = 'mapped'
      and status in ('trialing', 'active', 'past_due')
  ) candidates;

  update public.users set index_plan = resolved_plan, updated_at = now() where id = target_user_id;
  return resolved_plan;
end;
$$;
revoke all on function public.recompute_effective_index_plan(uuid) from public, anon, authenticated;
grant execute on function public.recompute_effective_index_plan(uuid) to service_role;

comment on table public.billing_manual_entitlements is
  'Explicit non-Stripe entitlement provenance; merged by highest valid plan.';
