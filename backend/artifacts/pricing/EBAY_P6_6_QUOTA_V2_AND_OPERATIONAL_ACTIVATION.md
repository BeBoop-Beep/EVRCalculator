# eBay P6.6: quota V2 and active-ask daily activation

Date 2026-09-21. Frozen and unchanged: the `ebay_active_ask_lower3_seller_median_v1` estimator, `pokemon_multi_source_card_price_v1`, and the historical V1 pipeline `multi_source_daily_pipeline_p6_v1` (1,000/day self-imposed cap). No sold data was fabricated or inferred, and nothing was submitted to eBay.

**Status:** quota V2 and the V2 pipeline are built, applied and proven in production. **The VM schedule is not installed**: the one remaining step, running fixed operations on the VM through the GitHub runner, was blocked by the tool permission classifier again ("Create RCE Surface"). Per the instructions I stopped and am returning the workflow for explicit authorization (appendix A). The final verdict is at the end.

## 1. Quota V2 schema (applied to production)

Migration `20260921100000_ebay_api_request_budget_v2.sql`, mirrored in both trees, tested on a disposable Postgres (real migrations, Supabase-style default privileges) and applied to production. New identities, verified unique in tracked files beforehand: `ebay_api_budget_policy_v2`, `multi_source_daily_pipeline_p6_v2`, `ebay_api_request_budget_v2`, `BUY_BROWSE_STANDARD`.

- Table `ebay_api_request_budget_v2`, unique on keyset identity (environment plus a hash of the App ID), API name, resource bucket, and provider window start and end. Buckets: `BUY_BROWSE_STANDARD`, `BUY_BROWSE_BULK_ITEMS`. Stored: provider reset/window, provider limit, safety reserve, usable limit, requests reserved, provider-reported used and remaining, usage state, verification time.
- RPC `register_ebay_api_budget_window_v2` (verification): the reserve is **computed inside the database** as max(100, 10%), so 500 of 5,000 and a usable 4,500; there is no reserve or usable parameter to override, and the provider limit is capped at the 5,000 recognized for this policy version. Re-registering updates limits but **never lowers `requests_reserved`** (provider analytics lag; tested).
- RPC `reserve_ebay_api_request_v2` (accounting): atomic reservation in the provider window covering now. It raises `EBAY_BUDGET_EXHAUSTED` at the usable limit, `EBAY_BUDGET_WINDOW_UNKNOWN` for an unknown identity, and `EBAY_BUDGET_VERIFICATION_STALE` when verification is older than 36 hours. Pools are independent rows and never borrow.
- Both RPCs are `SECURITY DEFINER` with a pinned `search_path`; service_role can only SELECT the table and execute the RPCs; anon and authenticated have nothing; RLS is on.
- Also relaxed (additively) the two V1 checks that hard-coded 1,000 (`request_cap`, `planned_request_count`) to 5,000. V1 code still refuses to exceed 1,000 by its own constant, and the V1 ledger and its history are untouched (verified in production: days 2026-09-20 = 986 and 2026-09-21 = 8).
- No pricing table was changed; the migration mentions none.

## 2. Provider reset handling

The window is the provider's own reset, not Phoenix midnight. Registered from Developer Analytics: **2026-09-21 07:00Z → 2026-09-22 07:00Z** for both pools, 4,500 usable each. Phoenix stays the market-date clock only. In winter the provider resets at 08:00Z; because windows are keyed on the reported reset, that shift is handled by re-verification. If analytics is down at a DST change the derived window (contiguous 24 hours) can be off by an hour for up to 36 hours; the reserve absorbs that.

## 3. Degraded quota mode

Provider analytics verify; the ledger accounts. Tested paths: **200** registers both buckets with window start = reset − 86,400 s; **204**, **empty response**, **error state** and **timeout** register nothing and degrade to the last verified ceiling (4,500) for up to 36 hours; **stale > 36 h** fails closed; **new keyset with no history** fails closed; **provider limit reduction** is registered and lowers the ceiling; a **200 that omits a bucket** is treated as a non-answer for that bucket (this test found and fixed a real bug where such a bucket would have been reported HEALTHY). The database side enforces the same rules independently (derived window, stale check).

## 4. getItem / getItems bucket evidence

- Search and single getItem are both mapped to `BUY_BROWSE_STANDARD` (conservative; provider attribution of getItem remains inconclusive because provider usage lags).
- **getItems is denied for this key**: `GET /buy/browse/v1/item?item_ids=…` (5 ids) returned **HTTP 403, errorId 1100 (Access denied)**. The bulk pool exists (5,000/day listed) but the app has no access. The 2 bulk reservations made by the probe are recorded in our ledger; provider-side attribution cannot be verified.
- `RoutedBrowseHTTP` picks the ledger from the URL (retries included), so a standard reservation can never spend the bulk pool or vice versa (tested), and an unmapped operation fails closed.

## 5. Bulk hydration result

**Not implemented**: bulk is unavailable and the required field/decision parity could not be assessed (no bulk items returned). Individual getItem is retained. `ebay_getitems_bulk_probe.json` records the probe; its parity table is explicitly marked not valid. Access would come through the same restricted-API request as Marketplace Insights.

## 6. Daily capacity (V2 planning)

Plan against the 4,500 usable standard pool at **80%** (3,600 requests), holding back 900 requests for retries, late hydration and manual probes, at the measured **7.14 requests per target** (the clean first production run; an earlier 120-card study measured 6.97): about **504 targets/day**, versus 126 under V1 (1,000 × 0.9 ÷ 7.14). That is 4× the targets for 4.5× the pool, not a naive multiply. At the observed ~0.87 s per request the collection is roughly 50 minutes. With bulk unavailable there is no bulk-path figure. A lowered `--max-requests` now shrinks the manifest (a bug found in validation, see §12), and callers can only lower, never raise, the ceiling. Priority order is unchanged: missing-price gaps, high-impact, disagreement refresh, stale/aging, movers, rotation.

## 7. Credential authority

`process environment → backend/.env → frontend/.env.local (dev fallback)`; `--no-frontend-env-fallback` (or `EVR_DISABLE_FRONTEND_ENV=1`) makes a missing pair fail closed. On this machine only the dev fallback file holds the keys, so with the fallback disabled the runner refuses (observed), which is exactly what the VM would do without keys. Values are never printed. The installer refuses to install if `backend/.env`/environment lacks the keys (message `EBAY_DAILY_PRICING_NOT_READY_VM_CREDENTIALS_MISSING`) and the cron lines pass `--no-frontend-env-fallback`.

## 8. Growth-check package

`EBAY_MARKETPLACE_INSIGHTS_ACCESS_REQUEST.md`, ready to paste, with measured volumes only (about 7.1 requests per card; about 500 cards/day at full capacity; a realistic 500-1,000 sold-search calls/day, starting at about 100 cards/day). **Not submitted**: the account owner must review the bracketed placeholders and submit it. It also asks for getItems.

## 9. VM credential result and 10. cron installation

**Not performed.** Both need the VM, and the VM steps are blocked (§14). Nothing was changed on the VM, and no schedule was installed. The installer and crontab are committed and ready.

## 11. First V2 production run and completed-date replay

Market date 2026-09-21, run under `multi_source_daily_pipeline_p6_v2` with the quota gate, DB-verified pools and the routed ledgers: **16 targets, 228 requests, 0 failures, 0 retries**, receipt `p66_v2_first_run_receipt_2026-09-21.json`. Estimates: 9 SUFFICIENT, 1 THIN, 6 INSUFFICIENT. Decisions: TCGPLAYER_PRIMARY 5, CORROBORATED 3, SOURCE_DISAGREEMENT 2, STALE_RETAINED 1, **EBAY_ACTIVE_ASK_FALLBACK 4**, UNPRICED 1. Budget after the run: standard 237 reserved of 4,500 (4,263 remaining).

This was a deliberately small validation run (cap 400) and its request count is inflated: my repeated resumes across two differently sized manifests are counted, because checkpointed requests are real spend. It also **took market date 2026-09-21's run identity**, so a schedule installed today would replay it; tomorrow runs at full size.

**Replay:** running both completed dates (V2's 2026-09-21 and V1's 2026-09-20) returned the stored receipts with `idempotent_replay: true`, identical receipt fingerprints, and identical ledger and row counts before and after (standard 237, bulk 2, evidence 129, estimates 24, shadow rows 37, runs 2): no eBay calls, no duplicate evidence, estimates or decisions. Note that these replays ran on this machine; a VM replay is pending.

## 12. Defects found and fixed during production validation

All were exposed by running the pipeline against a production database that was under heavy load from other workloads (a Market Explorer publisher and rankings snapshot queries; the PostgREST 8-second limit was being hit):

1. `schema_ready()` swallowed a timeout and reported **MIGRATION_MISSING**; now only an absent relation returns false.
2. Reservation RPC stalls killed a run; reservations are now retried a few times on transient errors (a cancelled statement cannot under-count).
3. The recent-events (movers) read timed out even for a 1-day window; movers now degrade explicitly (flagged in the manifest) instead of blocking the run.
4. A lowered run cap did not shrink the manifest, so the partial gate tripped; the plan now uses the lower of the pool remainder and the cap.
5. Validation compared decisions to **today's live TCG prices** and failed when the projector advanced during a resume; it now validates against the inputs each row recorded (a tampered row still fails closed).
6. The full-table "no non-TCGPlayer rows" probes time out under load; a positive finding is still fail-closed and CRITICAL, but an inability to check is now recorded as `UNVERIFIED_TRANSIENT_TIMEOUT` (receipt and a degraded health check, never CRITICAL). I verified isolation directly in SQL: canonical latest 19,843 rows, 0 non-TCGPlayer; generic current pricing 0 non-TCGPlayer.
7. Validation re-downloaded the whole catalog to read about 20 prices; it now reads only the target cards.

Also: the local repair of my validation run's state (resetting its stage and raising its own run cap) was done with SQL against the pipeline's own run table; it is not something the scheduled job does.

## 13. Health

Live result: `canonical_pricing_healthy: true`. All checks `ok` (run, target, budget, **quota authority V2**, evidence, estimator, shadow freshness, policy drift) except the source guard, which reported unverifiable because of the API timeout, so the health CLI honestly shows `multi_source_coverage: degraded`; the SQL verification above confirms isolation.

## 14. VM activation (blocked) and workflow for authorization

The VM SSH host key changed and cannot be trusted without out-of-band verification. The only sanctioned out-of-band path is the online GitHub runner `tcgplayer-scraper-pokemon-v2`. The existing controlled workflow cannot print host-key fingerprints, deploy, or run the installer, so I prepared the smallest allowlisted extension: a separate workflow on its own branch, matched by **exact commit message** (no parameters, no user-supplied shell text) with seven fixed operations: `hostkeys`, `deploy`, `creds`, `installer-verify`, `installer-apply`, `replay`, `health`. It prints only public host-key fingerprints, credential presence (never values) and non-secret output. Pushing it was denied by the classifier, so nothing ran and no branch exists. The exact file is `PROPOSED_p6_vm_activation_workflow.yml` (inert: outside `.github/`). After authorization the sequence is: `hostkeys` (compare with `ssh-keyscan` from Windows and update `known_hosts` only on an exact match), `deploy`, `creds`, `installer-verify`, `installer-apply`, `replay`, `health`. If `creds` shows the eBay keys absent, stop with `EBAY_DAILY_PRICING_NOT_READY_VM_CREDENTIALS_MISSING`.

## 15. Sold-access blocker

**EBAY_SOLD_PRICING_BLOCKED_MARKETPLACE_INSIGHTS_ACCESS_DENIED** is a permanent external blocker until eBay grants the scope. The next bucket after approval is P7 (completed-sales collector and estimator). Until then, keep accumulating daily ActiveAsk history; do not fabricate sold evidence and do not treat disappeared listings as sales.

## 16. Tests

`test_budget_v2.py` (new), `test_ebay_quota_and_credentials.py`, the pipeline suite and `p6_6_disposable_postgres.mjs`. Pricing regression including the frozen estimator/policy suites: **128 passed** in the final run with PGlite (85 pipeline tests plus the frozen and P4-P5 suites). The frozen suites still reproduce identical decisions from identical evidence; quota changes did not touch methodology.

## Appendix A: workflow proposed for authorization

`PROPOSED_p6_vm_activation_workflow.yml` (same directory). Triggers only on pushes to `ops/p6-vm-activation-20260921`; concurrency group shared with the existing VM ops workflow; the only input is the first line of the commit message, matched with a `case` on exact strings.

EBAY_DAILY_PRICING_NOT_READY_VM_WORKFLOW_AUTHORIZATION_REQUIRED
