set local lock_timeout = '1s';
set local statement_timeout = '30s';

create index if not exists sealed_product_price_observations_product_date_id_idx
  on public.sealed_product_price_observations (sealed_product_id, captured_at, id);
