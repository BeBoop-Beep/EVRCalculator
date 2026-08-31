-- Billing foundation only: no Stripe API integration, checkout, or pricing.
create table public.billing_customers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  provider text not null check (provider = 'stripe'),
  provider_customer_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider),
  unique (provider, provider_customer_id)
);

create table public.billing_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  billing_customer_id uuid not null references public.billing_customers(id) on delete restrict,
  provider text not null check (provider = 'stripe'),
  provider_subscription_id text not null,
  provider_product_id text,
  provider_price_id text,
  offer_key text not null,
  plan text not null check (plan in ('plus', 'premium')),
  status text not null,
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  canceled_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_subscription_id)
);
create index billing_subscriptions_user_id_idx on public.billing_subscriptions(user_id);
create index billing_subscriptions_status_idx on public.billing_subscriptions(status);

create table public.billing_webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null check (provider = 'stripe'),
  provider_event_id text not null,
  event_type text not null,
  processing_status text not null check (processing_status in ('received', 'processing', 'processed', 'failed')),
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  error_code text,
  error_summary text,
  unique (provider, provider_event_id)
);

alter table public.billing_customers enable row level security;
alter table public.billing_subscriptions enable row level security;
alter table public.billing_webhook_events enable row level security;
revoke all on public.billing_customers from anon, authenticated;
revoke all on public.billing_subscriptions from anon, authenticated;
revoke all on public.billing_webhook_events from anon, authenticated;

comment on table public.billing_customers is 'Server-owned provider customer identities; never contains card data.';
comment on table public.billing_subscriptions is 'Server-owned subscription audit state; users.index_plan remains effective entitlement.';
comment on table public.billing_webhook_events is 'Minimal idempotency ledger; provider payloads are intentionally not stored.';
