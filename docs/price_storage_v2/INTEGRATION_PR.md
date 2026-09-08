# Price Storage V2 integration — draft, no production cutover

## Current milestone: live canary defect understood; forward-only date-safe v2 passes

The frozen migration-source window `20260905235956`–`20260906233651` remains
fully reconciled: all **89** applied records match their original SQL checksums and
the independent manifest `d988d2e6e877d3373f613d2351e86339`. The exact historical
migration SQL remains unchanged and must not be replayed merely because its source
files are now present.

## Live September 6 canary result

The production read-only canary for **Evolving Skies**, **Crown Zenith + Galarian
Gallery**, and **Celebrations + Classic Collection** showed strong Price Storage V2
as-of health but exposed one flaw in the original scope acceptance contract.

For all three roots:

- raw-only rows = `0`;
- V2-only rows = `0`;
- missing prices = `0`;
- canonical review-required rows = `0`;
- scrape and shadow receipts were complete and had matching source completion timestamps.

Accepted Sep 6 combined-root candidates remained:

- Evolving Skies Standard `$8,305.06` / 237, Top10 `$6,596.25` / 10;
- Crown Zenith Standard `$2,634.47` / 230, including 70 subset cards, Top10 `$1,432.66` / 10;
- Celebrations Standard `$624.16` / 50, including 25 subset cards, Top10 `$512.14` / 10.

However the historical `canonical_asof_scope_split_v1` preview blocked all three with
`live_root_contract_mismatch`. Its `live_root_only_rows` / `proposed_root_only_rows`
were `237/237`, `229/229`, and `48/48` respectively.

The reason is architectural rather than price-compression corruption: v1 compares an
**approved-date as-of reconstruction** against the moving
`get_pokemon_market_root_set_card_prices_latest_v1` contract, including latest
captured dates and storage provenance. Once that moving latest projection advances
past the approved Market date, every otherwise-correct approved-date row can appear
different.

## Forward-only date-safe v2

The already-applied v1 migration remains untouched for auditability. New review-only
proposal `backend/db/proposals/price_storage_v2_scope_stage_v2.sql` adds:

- `preview_price_storage_v2_scoped_values_v2(uuid,date)`;
- `stage_price_storage_v2_scoped_values_v2(uuid[],date)`.

`canonical_asof_scope_split_v2` preserves the existing fail-closed checks for:

- approved Market date;
- edition-split roots;
- raw/V2 as-of resolver definition hashes;
- exact source scrape + V2 shadow receipts;
- raw↔V2 as-of row parity;
- duplicate price identities;
- missing prices;
- review-required canonical cards;
- root identity `(canonical_card_id, member_set_id)`.

It changes only the invalid moving-latest portion:

- storage provenance `source` is not treated as an economic field;
- if the latest root contract has **not** advanced past the approved date, normalized
  latest-root economic rows must still match exactly;
- if the latest root contract **has** advanced past the approved date, newer latest
  economics are diagnostic rather than evidence that the approved-date reconstruction
  is wrong;
- root identity and raw↔V2 approved-date parity must still be exact before v2 can pass.

The separated immutable writers now require v2 staged evidence and re-run the v2
preview before insertion. The producer coordinator uses v2 staging and still contains
**no scheduler attachment**.

## Exact PostgreSQL acceptance

GitHub Actions run `34183532432`, job `101927253176`, succeeds on PostgreSQL 17.6.
The suite now contains **95 passing checks**:

- **42** integration/unit checks;
- **13** migration/source/full-ledger checks;
- **6** Set Value snapshot replay safeguards;
- **20** writer/permission/concurrency checks;
- **8** exact restored-source SQL checks;
- **6** fail-closed coordinator checks.

Pattern Overlay Guardrails also pass on the validated feature implementation.

The new exact-source regression reproduces the production failure mode by advancing
the actual modern standard-root latest projection (`pokemon_canonical_card_market_prices_latest`)
to Sep 7 while leaving Sep 6 historical V2 events/ranges unchanged. It proves:

1. the actual root latest reader changes;
2. historical v1 blocks with `live_root_contract_mismatch`;
3. Sep 6 raw↔V2 as-of parity remains exact;
4. root identity remains exact;
5. v2 marks moving-latest economics non-applicable to Sep 6 acceptance and passes;
6. identity or approved-date as-of differences would still block.

## Snapshot replay and coordinator

The production Set Value snapshot builder has an internal diagnostic-only current-day
root override. Normal production calls still default to no override. Six safeguards
prove only explicitly supplied current-day roots change in memory; history and unrelated
roots remain unchanged; child/subset IDs, duplicate roots, wrong dates/scopes and invalid
values fail closed.

The review-only producer coordinator:

- checks the disabled release gate before staging;
- stages through v2;
- publishes member/root destinations atomically per invocation;
- rolls back the whole invocation if one requested root blocks;
- is idempotent on exact repeat;
- denies public roles;
- has no cron attachment and reports `public_routing_changed=false`.

## Production safety

No v2 proposal has been installed in production. No release gate has been enabled.
No cron has been attached. No public reader has been switched. No scrape, simulation or
snapshot publication was launched by this work. No historical/raw price rows were
rewritten or deleted.

## Remaining release gates

1. Run a small **live read-only diagnostic** to confirm the production moving latest
   root projection is newer than approved Sep 6 for the three canaries and that the
   observed v1 mismatch is the same date-boundary condition proven in PostgreSQL.
2. If confirmed, convert only the forward v2 stage + separate destination/writer/
   coordinator proposals into **new** executable migrations, with the release gate
   still disabled and no scheduler attachment.
3. Run Supabase security/performance advisors and explicit ACL/RLS verification.
4. Run the actual live dry snapshot/index replay using v2 root candidates; persist nothing.
5. Approve a bounded producer cutover with rollback; only afterward consider scheduling.
6. Observe stable daily cycles before retiring legacy direct-reader, rebuild-script and
   fallback dependencies.
7. Reclaim physical storage only after destructive-retirement acceptance; logical delete
   alone does not shrink the database files.

Do not merge this PR yet.
