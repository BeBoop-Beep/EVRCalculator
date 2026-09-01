# Market Explorer Effort 1: variant execution engine

## Root cause

The old interactive authority resolved one selected variant per canonical card,
partitioned price validity by `canonical_card_id`, and derived latest-before-day
prices while serving a query. That shape both collapsed independently priced
variants and scaled with cards multiplied by dates. The application then added
a 250-card unranked rejection to avoid the resulting statement timeout.

## Identity contract

Raw Card Market uses `card_variant_id` as the traded instrument. The canonical
card remains metadata and the Pokemon-membership authority. Near Mint (`name =
'Near Mint'`, `abbreviation = 'NM'`) USD is the sole pricing condition.

Canonical-to-legacy resolution is centralized in this order:

1. reviewed `pokemon_canonical_card_legacy_identity_links`;
2. parent Pokemon TCG API identity;
3. variant Pokemon TCG API identity;
4. the existing normalized name/number compatibility fallback.

The winning legacy card expands to every authoritative `card_variants` row.
No condition rows are created as constituents.

## Read model

`pokemon_card_variant_market_price_intervals` stores one row per winning daily
Near Mint USD observation with `[valid_from, valid_to)` validity. Same-day
duplicates select the newest `(created_at, id)` deterministically. Validity is
partitioned by `card_variant_id`, so First Edition, Unlimited, normal, holo,
reverse-holo, stamped, and special variants never supersede one another.

The model is smaller than a variant-by-calendar-day Cartesian table and moves
latest-before-date resolution into publication/backfill. Interactive queries
join the canonical Market quality dates to indexed validity intervals, apply
scope/rarity/Pokemon/price/release intersections, then rank survivors by price
and `card_variant_id`. Common-cohort joins also use `card_variant_id`.

## Live read-only audit (2026-08-30)

- Canonical cards: 20,651
- Resolved canonical cards: 19,983 (96.765%)
- Unresolved: 668
- Explicit legacy links: 56
- Parent API identity: 19,550
- Name/number compatibility fallback: 377
- Resolved variants: 35,172
- Canonical cards with multiple variants: 13,789
- Ambiguous candidates at the winning identity tier: 151, resolved by stable
  legacy-card UUID ordering and retained as audit debt
- Editions: 837 First Edition, 839 Unlimited, 33,496 unspecified
- Printing: 8,298 holo, 13,915 non-holo, 12,959 reverse-holo
- Special treatments: 581 mapped variants, including Master Ball, Pokeball,
  ACE SPEC, and stamped variants

The existing canonical latest-price table selects 19,764 of these variants by
design and therefore cannot measure complete variant price coverage. A broad
read of `card_market_usd_latest_by_condition` timed out. The bounded requested
examples all had positive Near Mint price history.

## Requested examples

- Expedition Base Set Dragonite #43 resolves to distinct non-holo and
  reverse-holo variants; both have Near Mint history.
- Dragon Dragonite ex #90 resolves to its independent holo variant with Near
  Mint history.
- Fossil Kabutops #24 resolves to separate First Edition, Unlimited, and
  unspecified non-holo variants; all have Near Mint history.
- Legendary Collection Dewgong #40 resolves to distinct reverse-holo and
  non-holo variants; both have Near Mint history.

Exact IDs and reproducible current counts are emitted by
`backend/scripts/audit_market_explorer_variant_identity.py`.

## Deployment and performance status

### Effort 1B deployment-safe publication

The `20260829210512` migration now deploys schema and RPCs only. It contains no
historical refresh. An omitted or empty variant scope is a no-op, so a missing
PostgREST argument cannot accidentally rebuild the catalog. A bounded refresh:

1. deletes intervals only for `card_variant_id = ANY(p_card_variant_ids)`;
2. limits canonical authority work to the requested variants' owning sets;
3. chooses one same-day winner by `(created_at DESC, observation UUID DESC)`;
4. rebuilds `[valid_from, valid_to)` independently per variant; and
5. inserts nothing, without failing, for a requested variant with no positive
   Near Mint USD history.

`refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[])` is a
distinct service-only convenience RPC for bounded operational/daily set refresh.
It is intentionally not an overload of the variant RPC.

Historical publication uses
`backend/scripts/backfill_market_explorer_variant_intervals.py`. It orders sets,
then variants, by UUID and commits one variant batch per RPC call. The default
batch size is 100. Every successful batch logs elapsed time and a deterministic
`SET_UUID:VARIANT_UUID` cursor. `--resume-after` skips only durable successes.
The runner stops on its first failure and prints the exact failed variant IDs,
so a later resume cannot silently jump over them. Re-running a batch replaces
only that batch and is idempotent.

Examples (run from repository root):

```powershell
# Read-only plan for one deliberately small set.
python backend/scripts/backfill_market_explorer_variant_intervals.py `
  --dry-run --set-id <SMALL_SET_UUID> --batch-size 25

# Publish that pilot in separate transactions.
python backend/scripts/backfill_market_explorer_variant_intervals.py `
  --commit --set-id <SMALL_SET_UUID> --batch-size 25

# Resume the catalog after the last durable cursor printed by a prior run.
python backend/scripts/backfill_market_explorer_variant_intervals.py `
  --commit --batch-size 100 --resume-after <SET_UUID:VARIANT_UUID>
```

The script requires backend service-role credentials. It grants no frontend or
public access and dry-run never calls the refresh RPC.

### Daily incremental integration point

The smallest integration is in
`backend/db/repositories/card_variant_prices_repository.py`, inside
`_refresh_pokemon_set_value_history_for_price_rows`. That function already runs
only after `insert_card_variant_prices_batch_with_stats` has successfully
reconciled writes, and its `changed_rows` already contains the exact affected
variant IDs. After the existing set-value and canonical-latest refresh calls,
invoke `refresh_pokemon_card_variant_market_price_intervals` with that same
deduplicated `variant_ids` list. Keep its existing warning/retry posture so a
derived-read-model refresh is observable but cannot reinterpret a failed price
write as successful. This is the preferred daily path; the set-scoped RPC is an
operator fallback when replaying or repairing a whole set.

No scraper integration was added in Effort 1B. The alternative postcondition
hook is immediately after `verify_tcgplayer_source_variant_persistence` succeeds
in `backend/scripts/run_pokemon_set_scrape.py`, but that is less precise because
it refreshes every variant in the set rather than only changed price rows.

### Exact safe deployment and acceptance order

1. Deploy only
   `supabase/migrations/20260829210512_market_explorer_filtered_card_cohorts.sql`
   through the repository's normal migration pipeline. Do not append a refresh
   statement and do not run a catalog backfill from migration tooling.
2. Verify the interval table has RLS enabled; `anon` and `authenticated` have no
   table privileges or function execution; `service_role` alone can select,
   insert, delete, and execute the three operational/query RPCs.
3. Dry-run one small set, then commit it with batch size 25.
4. Inspect interval counts, distinct variants, min/max validity, condition,
   currency-source expectations, and variant-specific `valid_to` chains.
5. Execute the variant cohort RPC for that set and compare a cohort containing
   only one compatible variant per canonical card with the legacy RPC.
6. Repeat for Fusion Strike and Evolving Skies before catalog publication.
7. Run the full backfill in batches of 100, retaining logs and the last cursor.
8. Reconcile coverage, then run the requested cold-ish/warm benchmark matrix and
   `EXPLAIN (ANALYZE, BUFFERS)` directly over representative SQL.

Acceptance reporting must include canonical/resolved cards and variants,
variants with Near Mint USD history, interval rows and date extent, sets,
edition/printing/special counts, plus named/high-value analysis of the 668
unresolved and 151 ambiguous mappings. Benchmark scopes are: small set, Fusion
Strike, Evolving Skies, their union, 3 and 10 selected sets, full Sword & Shield,
full Scarlet & Violet, all Raw Cards, Dragonite global, global rarity, era plus
rarity, Dragonite plus era plus rarity, global price/release-age segments, and a
broad Top 10. Record cold-ish DB time, subsequent DB time, returned rows, API
wall time, and plans/buffers; targets remain 2–3 seconds common and 3–5 seconds
for broad interactive queries.

### Environment status

The migration remains unapplied. Production access available to this worktree
is REST/service-role only; there is no Supabase CLI, linked project, direct
PostgreSQL URL, `psql`, Docker, or Podman. Consequently no representative schema
deployment, backfill timing, post-backfill coverage, cohort parity,
`EXPLAIN (ANALYZE, BUFFERS)`, or performance benchmark is claimed here.

Do not deploy the frontend identity treatment until a representative database
has applied the migration through the normal deployment path, recorded the
backfill cardinality/storage cost, proved one-variant legacy parity, and met the
cold-path scope benchmarks from the Effort 1 acceptance matrix.
