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

The corrected `20260829210512` migration remains unapplied. Production access
available to this worktree is REST/service-role only; there is no linked CLI
project, direct PostgreSQL URL, `psql`, Docker, or Podman. Consequently the new
table cannot be backfilled safely and the new RPC cannot be benchmarked or
examined with `EXPLAIN (ANALYZE, BUFFERS)` here.

Do not deploy the frontend identity treatment until a representative database
has applied the migration through the normal deployment path, recorded the
backfill cardinality/storage cost, proved one-variant legacy parity, and met the
cold-path scope benchmarks from the Effort 1 acceptance matrix.
