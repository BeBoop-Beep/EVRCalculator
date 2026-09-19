# eBay daily pricing P3: database evidence persistence

Market date: 2026-09-19. Branch: `develop`. This is source evidence storage only; no eBay source-price estimator, combined price, or inDex Fair Value output exists here.

## Schema and migrations

Additive migrations, byte-identical in `supabase/migrations` and `backend/db/migrations`:

1. `20260919212129_ebay_pricing_evidence_v1.sql`
2. `20260919212741_restrict_ebay_pricing_evidence_privileges.sql`

Both were applied to the connected Supabase project. The second migration removes inherited service-role DELETE/TRUNCATE grants found in the live grants audit. No canonical pricing table was changed by either migration.

`ebay_pricing_runs_v1` holds a UUID run key, market date, lifecycle status, selector and collector versions, fingerprints, planned and actual request counts, raw/deduped/identity/language counts, timestamps, artifact provenance, and `production_authority=false` enforced by a check. `ebay_card_listing_evidence_v1` holds one compact active-ask observation per `(run_id, canonical_card_id, listing_item_id)`, with UUID foreign keys to run, canonical card, optional card variant, and optional condition. It records explicit USD item/shipping/landed amounts, URLs, title, buying options, condition text, a SHA-256 seller key, query provenance, and separate identity, language, and eligibility states and policy fingerprints. A database check forbids `landed_ask_usd` without a shipping amount and requires exact item-plus-shipping arithmetic. `ebay_card_pricing_run_summary_v1` holds one diagnostic row per run/card, including rejected counts and eligible ask range/median. Those diagnostics are **not** an eBay market price.

The listing table has the unique replay key plus four read indexes: canonical card/date, variant/date when resolved, eligibility/date, and item ID. The run and card-summary primary keys provide their run lookups. All three tables have RLS enabled. `anon` and `authenticated` have no grants; `service_role` has only SELECT, INSERT, and UPDATE. No public listing endpoint or seller username is stored.

## Artifact and retention policy

Full eBay response JSON remains in collector run artifacts. Postgres stores only normalized, identity-qualified `ENGLISH_ELIGIBLE` and `LANGUAGE_UNRESOLVED` active asks with valid USD item prices. Explicit non-English and identity-rejected listings remain in raw artifacts and contribute to card/run rejection counts. Missing shipping remains NULL, including landed ask; explicit USD zero shipping yields item price as landed ask. An active ask is never represented as a completed sale.

The [persistence service](../../scripts/persist_ebay_daily_pricing_evidence.py) validates the selector fingerprint, target list, frozen query plan, run/cohort fingerprint, matcher mode, listing provenance, eligibility enums, and policy versions before any write. `--dry-run` performs parsing, normalization, and projection without opening a DB client. `--persist` upserts run, listing, and summary rows. A replay with changed run or summary fingerprints is rejected. A failed first evidence write marks the run FAILED; a failure after some rows were written marks it PARTIAL for safe retry. It never addresses canonical price tables.

## Volume projection

The 150-target P1 plan uses a maximum of 200 captured hits per target. The two-target smoke reached 400 raw and deduped hits and 14 identity-qualified, language-unresolved hits. Scaling this observed rate to 150 targets gives an upper-activity illustration, **not** a forecast of the full target mix. The 14 stored rows averaged 945 heap bytes; the planning allowance is 1,500 bytes per row including index/row overhead. Existing fixed table and index pages are excluded from linear estimates.

| Retention scenario | Rows/day at scaled smoke rate | Rows/30 days | Rows/365 days | Approx. GiB/year |
| --- | ---: | ---: | ---: | ---: |
| All raw hits | 30,000 | 900,000 | 10,950,000 | 15.30 |
| All deduped hits | 30,000 | 900,000 | 10,950,000 | 15.30 |
| Identity-qualified hits | 1,050 | 31,500 | 383,250 | 0.54 |
| English-eligible plus unresolved | 1,050 | 31,500 | 383,250 | 0.54 |
| English-eligible only, observed sample | 0 | 0 | 0 | 0 |
| **Chosen P3 persisted contract** | **1,050** | **31,500** | **383,250** | **0.54** |

The zero English-eligible row count is caused by Browse search summaries lacking structured language metadata. It is not an estimate that future enriched runs will have zero usable listings. P4 will need bounded item-detail language enrichment before a source estimator can use these rows.

## Dry run and bounded live smoke

The dry run of run `227df0380f8246d29715b2a7202a711a` made zero DB writes and projected 400 raw, 400 deduped, 14 identity-qualified, 0 English-eligible, 14 language-unresolved, and 14 persisted rows. The live collector used two P1 targets and four successful Browse calls (zero failures, zero retries) under its ten-call smoke cap. The persistence service inserted one COMPLETE run, 14 normalized listing rows, and two card summaries. A second `--persist` invocation returned the same run fingerprint `b1a73ffdc4d42ff204a56012f15bcf70901b237d2ef63ca390b2237dd7e45b5b`; a database count still showed exactly one run, 14 evidence rows, and two summaries. The production-authority flag is false.

## Canonical pricing safety

Before and after the smoke, catalog row estimates and relation sizes were unchanged for all three canonical pricing tables: observations 17,663,552 estimated rows / 9,259,974,656 bytes; events 3,031,087 / 931,340,288 bytes; current 167,887 / 60,047,360 bytes. PostgreSQL mutation counters (`n_tup_ins`, `n_tup_upd`, `n_tup_del`) remained zero for each table during this validation. Exact post-smoke existence queries found no source other than `TCGPlayer` in observations, events, or current. A full sorted fingerprint query over the large canonical tables timed out, so the evidence is the unchanged catalog metrics, mutation counters, exact source checks, and the service's isolated table access rather than a whole-table checksum.

## Tests and P4 handoff

Focused tests cover run/evidence insertion and replay, changed-artifact rejection, duplicate matches, nullable and explicit free shipping, landed arithmetic, active-ask and eligibility enforcement, unresolved persistence, rejected retention, summaries, failed and partial status, volume projection, and isolation from canonical pricing tables: **30 passed**. Live database checks confirmed all four foreign keys on listing evidence and the RLS/grant model.

P4 may read: `run_id`, `market_date`, `canonical_card_id`, `card_variant_id`, `condition_id`, `listing_item_id`, `captured_at`, `marketplace`, `item_price_usd`, `shipping_price_usd`, `landed_ask_usd`, `currency`, `buying_options`, `condition_text`, `seller_key_sha256`, `identity_state`, `language_state`, `english_market_eligibility_state`, all policy versions/fingerprints, and the card-run depth counts. It must use only explicitly English-eligible rows with a valid landed ask for an English source estimator, define that estimator separately, and retain TCGplayer as an independent source.

EBAY_DAILY_PRICING_DB_PERSISTENCE_READY_FOR_SOURCE_ESTIMATOR
