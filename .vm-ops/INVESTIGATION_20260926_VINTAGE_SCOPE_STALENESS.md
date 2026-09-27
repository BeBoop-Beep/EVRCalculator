# Vintage Market scope staleness — September 26, 2026

Status: INVESTIGATED; no publication/history data or production schedules changed in this pass. Existing collection/projection workers were left alone. This is not a deployed-fix or freshness-completion receipt.

## Scope and live authority

User asked about 1st Edition, then explicitly expanded scope to Unlimited and Shadowless. Bounded read-only Supabase SQL used statement_timeout=5s and lock_timeout=1s. The initial clock was 2026-09-27 00:40:57.835364 UTC = September 26 17:40:57 America/Phoenix. PostgreSQL was responding, not in recovery, with no other active queries; postmaster start remained 2026-09-26 03:47:00.323649 UTC.

September 26 batch 64 is complete/promoted, 167/167 successful; September 25 batch 63 also complete/promoted. All ten vintage parent Sets have completed scrapes for both dates and completed canonical price projections for September 25. At the edition-source check, September 26 projections were complete for eight vintage parents; Base and Gym Challenge were still pending. Those are collection/projection statuses, not edition-history certification verdicts.

## 1. Confirmed missing daily root-history stage

Table public.pokemon_market_root_set_value_daily_history_v2_shadow:
- first_edition: 10 distinct Sets, latest market_date 2026-09-24; 10 rows on September 24, zero on September 25 or 26.
- unlimited: 10 distinct Sets, latest market_date 2026-09-24; 10 rows on September 24, zero on September 25 or 26.
- shadowless: one Set, latest market_date 2026-09-24; one row on September 24, zero on September 25 or 26.
- standard rows in THIS history store are also capped at September 24 (150 Sets). This is distinct from the Standard history table used for the current public snapshot.

The latest write across all scopes was 2026-09-24 21:30:02.006151 UTC. The latest price_storage_v2_root_history_sync_state record is September 24, complete, 171 synced rows, 167 source and projection Sets. There is no September 25 or 26 sync receipt.

Live get_pokemon_market_root_set_value_daily_history_v1 reads the above stored history table; its bulk wrapper sorts by set_id,market_scope,market_date.

Live sync_price_storage_v2_root_history_latest selects the newest READY/LEGACY_VERIFIED market date, checks completed source/projection counts, and materializes root latest values into that date. run_price_storage_v2_shadow_cycle calls this root-history sync. Database cron job 19, price-storage-v2-shadow-cycle, runs every 15 minutes but remains active=false from emergency containment. The restarted staged per-Set price-projection path covers price events/current prices, observation ranges, intervals and canonical selected prices; it does not call the root-history sync. Restoring only those input stages therefore does not advance edition aggregate history.

September 25 is the newest READY Market quality date at inspection. All September 25 vintage source/projection jobs are complete, yet root history remains September 24. This identifies an additional missing derived-data handoff, not simply uncollected prices or another observed DB crash.

## 2. Public Market snapshot has two history sources

The persisted pokemon_explore_set_value_snapshot_latest row (tcg=pokemon,scope=market) has market_date=2026-09-25, updated_at=2026-09-25 23:34:57.604172 UTC, 156 root Sets and 167 market identities. Publisher SHA is 0ca31bab086f63f48b472d8119741619ad43d7ee.

Current main backend/scripts/build_pokemon_explore_set_value_snapshot.py blob 5ab57567ed0d63ea62c57462493d6f8546c054b7:
- _load_canonical_histories reads Standard markets from pokemon_set_value_daily_history, with explicit pagination.
- _load_scoped_certified_histories reads non-Standard markets through get_pokemon_market_root_set_value_daily_history_bulk_v1, in batches of four Set IDs, WITHOUT pagination.
- Noncertified dates are filtered. Incomplete current baskets are withheld. Histories with source-review holds retain only their latest certified point.

Persisted public entry results:
- Standard: 146 entries marked current as of September 25.
- 1st Edition: seven stale entries as of September 24; Base, Neo Destiny and Neo Revelation unavailable.
- Unlimited: six stale entries as of September 24; Jungle stale as of May 4; Base, Neo Destiny and Neo Revelation unavailable.
- Shadowless: Base entry unavailable, with no displayed current value/date.

Therefore the global snapshot's September 25 date does not establish per-edition freshness.

## 3. Confirmed API row truncation, not only stale histories

The first four sorted vintage root IDs used by the current reader are:
0010d2ec-894e-4c17-855d-5de6ff6fd204 (Base),
3562f9c9-f879-4d49-9d69-d0ab511230f9 (Neo Genesis),
37e1b616-c5f4-4279-83c4-ea8dcdd83c69 (Jungle),
42a3740d-4778-4857-9c28-e116f34b51f3 (Neo Destiny).

Direct SQL using the exact bulk RPC with start 1999-01-01/end 2026-09-25 returns 1,458 rows. The full data includes certified September 24 history for BOTH Jungle Unlimited and Neo Destiny Unlimited.

A read-only SQL reproduction using the function's ordering and LIMIT 1000 yields:
- Jungle Unlimited latest certified date = 2026-05-04.
- Neo Destiny Unlimited = no returned certified date/rows.

These reproduce the persisted public snapshot errors exactly.

Historical Supabase edge logs independently confirm the real publisher requests:
- 2026-09-25 23:34:23.591 UTC: POST bulk-history RPC, HTTP 200, response.headers.content_range = 0-999/*, no offset query parameter.
- 2026-09-25 23:34:23.954 UTC: POST same RPC, HTTP 200, content_range = 0-999/*, no offset.
- 2026-09-25 23:34:24.125 UTC: POST same RPC, HTTP 200, content_range = 0-647/*, no offset.

Thus a successful HTTP response was treated as the complete batch even though capped. The Standard reader's pagination was not carried over to the edition-specific reader. A proposed additional read-only VM reproduction workflow was blocked before creation; it did not execute. The actual historical response headers plus exact SQL reproduction provide the evidence above without that workflow.

## 4. Coverage and certification are separate remaining issues

All 21 edition stores stop at September 24, but six scopes have zero certified history days and do not become valid merely by relabeling the date:
- Base 1st Edition: September 24 coverage_pct 0.98, certified_on_date=false.
- Base Unlimited and Shadowless: coverage_pct 0, certified_on_date=false.
- Neo Destiny 1st Edition: coverage_pct 99.12, certified_on_date=false.
- Neo Revelation 1st Edition and Unlimited: coverage_pct 98.48, certified_on_date=false.

These are stored coverage/certification facts, not a complete diagnosis of source-identity/missing-price causes.

Neo Destiny Unlimited is DIFFERENT: 148 certified history dates through September 24 exist, with coverage_pct=100 and certified_on_date=true for that date. Its unavailable public value is reproduced by truncation, not by absence of certified data.

History source-review holds remain on Neo Discovery 1st Edition (4 blocking moves), Neo Genesis 1st Edition (1), and Team Rocket 1st Edition (1). These permit a latest certified point under the application contract but withhold the disputed full series. Do not remove those holds to make charts appear complete.

The newer run_price_storage_v2_scoped_publication_cycle is operator gated: price_storage_v2_scoped_release_gate.enabled=false. Its contract explicitly says scheduler_attached=false and public_routing_changed=false. Do not activate this separate unaccepted replacement merely because the current feed is stale.

## Repair requirements, not actions claimed here

1. Paginate the existing edition-history RPC using deterministic set_id/market_scope/market_date ordering and bounded pages. Detect short/capped/incomplete retrieval; add regression coverage for >1000 rows, late-sorted scopes, Jungle and Neo Destiny. Do not increase the project-wide API row cap as a workaround.
2. Restore an explicitly dated, bounded, scope-correct root-history materialization stage after canonical price projection and before public Market snapshots. Give it its own progress/failure records without blocking next-day raw collection.
3. Rebuild missing September 25/26 edition history from the correct as-of source lineage. Do NOT simply run the old latest-value sync against September 25 now: September 26 projections are already advancing, while its selected quality date remains September 25. It selects current/latest values, so blindly resuming it risks writing later prices under an older date.
4. Republish Market and validate EACH market key's as-of date; the overall snapshot date alone is insufficient. Keep genuinely incomplete and source-review-held scopes explicit and truthful.
5. Coordinate with still-held downstream Market/Explorer recovery. This read-only investigation did not clear holds, rebuild data, change collection throughput, or republish snapshots.
