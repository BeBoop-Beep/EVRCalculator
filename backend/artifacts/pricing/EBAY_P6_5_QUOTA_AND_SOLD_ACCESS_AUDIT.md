# eBay P6.5: real quota and completed-sales access audit

Date 2026-09-21. Machine-readable evidence: `ebay_quota_and_sold_access_audit.json` and `ebay_getitem_bucket_probe.json`. Frozen V1 (ActiveAsk estimator, policy, the 1,000/day V1 cap) was not changed. No cron was installed, nothing was pushed, and no sold estimator or Fair Value work was done. All probes were tiny and bounded: 5 token requests, 8 Browse calls (each reserved on the shared DB ledger), 10 analytics reads and 1 Marketplace Insights request. No tokens or secrets were stored or printed.

## 1. The keyset and its entitlements

- **Environment:** PRODUCTION (the App ID embeds `PRD`). The App ID and secret were never printed.
- **OAuth:** client-credentials application token, scope `https://api.ebay.com/oauth/api_scope`, 7,200 s. This is what the pipeline uses; no user token exists.
- **Browse API:** works (search and getItem both returned 200).
- **Marketplace Insights:** **not entitled** (§4).
- **Credential source on this machine:** only `frontend/.env.local` holds the eBay keys; `backend/.env` and the process environment do not. The VM was not inspected in this task.

## 2. Real quotas (provider Developer Analytics `getRateLimits`)

The call returned HTTP 200 with real data, so the known 204 problem did not occur here. It is still handled: a 204 or empty body is recorded as `PROVIDER_USAGE_UNRESOLVED_NO_CONTENT` ("not zero, not unlimited") and never becomes a quota.

| Bucket | Daily limit | Window | Reset |
|---|---:|---|---|
| `buy.browse` (all Browse methods except getItems) | **5,000** | 86,400 s | 2026-09-22 07:00:00Z |
| `buy.browse.item.bulk` (getItems) | **5,000** | 86,400 s | same |
| `buy.marketplaceinsight` | 5,000 (listed) | 86,400 s | same |
| `developer.analytics.app_rate_limit` | 5,000 | 86,400 s | same |

Our pipeline's 1,000/day cap is a self-imposed budget and uses 20% of the real Browse quota. The reset is midnight Pacific *daylight* time: it equals Phoenix midnight only while Pacific is on DST. In winter the provider resets at 08:00Z while a fixed UTC−7 Phoenix day resets at 07:00Z, so a Phoenix-day ledger would misalign by an hour. The V2 ledger therefore keys on the provider's reset time.

The analytics response lists a bucket for every API the platform offers (Trading, Sell, Feed, and others), including `buy.marketplaceinsight`. **Presence of a bucket is not entitlement**; that is why access was probed separately.

**Provider usage is not real time.** `buy.browse` moved 0 → 1 within 20 seconds of the first search, then stayed at 1 for more than 10 minutes across 8 Browse calls in total (2 searches, 6 getItem). The provider counter therefore cannot be used for per-request accounting, only to verify the ceiling and keyset identity. The local ledger stays the accounting authority. I could not cross-check against the developer-account report UI from here.

## 3. Browse pool mapping

| Operation we call | Bucket | Evidence |
|---|---|---|
| `GET /item_summary/search` (search) | `buy.browse` | observed +1 within 20 s |
| `GET /item/{id}` (getItem, detail hydration) | `buy.browse` per eBay's split (only getItems is separate) | **not observed debiting it**; six calls left `buy.browse.item.bulk` at 0, so the getItems pool is not touched. Attribution from provider data is **inconclusive** because of the lag above |
| `GET /item?item_ids=` (getItems) | `buy.browse.item.bulk` | not used by our pipeline |

For planning, treat getItem as debiting `buy.browse`. That over-counts if the assumption is wrong, which is the safe direction.

## 4. Marketplace Insights (completed sales): DENIED

- Token request with scope `buy.marketplace.insights`: **HTTP 400 `invalid_scope`** ("exceeds the scope granted to the client").
- `GET /buy/marketplace_insights/v1_beta/item_sales/search?q=pokemon card&limit=1` with the base token: **HTTP 403, errorId 1100, ACCESS, "Access denied / Insufficient permissions to fulfill the request."**

No sold data was returned, so the endpoint's response fields, history horizon, pagination, filters, Best Offer transaction-price handling and quantity information cannot be documented from evidence, and none are inferred. Nothing was scraped, and no sale was inferred from disappearing listings. Access requires eBay's restricted-API approval; the documentation pages could not be fetched from here (HTTP 403), so the exact current procedure is unverified.

## 5. Growth / restricted-access request (prepared, not submitted)

The submission text is in the JSON under `growth_request_preparation`. In short: purpose is Pokémon trading-card market pricing and index analytics; data use is per-card active-ask and (if approved) sold-price evidence, with no resale of raw listings; retention is normalized evidence rows in the database and raw responses on the VM only; identity protection is SHA-256 seller keys with no usernames stored; security is application-token-only access, secrets in the environment, RLS on all tables; volume is about 1,000 Browse calls/day today, with efficiency measures (shallow search then selective getItem, stop at 5 eligible sellers, persistent ledger). An owner needs to decide whether to submit and to confirm the current process on eBay's developer site.

## 6. Credential authority (Part I)

`backend/pricing_pipeline/ebay_credentials.py` resolves credentials in this order: process environment, `backend/.env`, then `frontend/.env.local` as a development-only fallback. A source is used only if it has both keys. The fallback can be disabled with `--no-frontend-env-fallback` or `EVR_DISABLE_FRONTEND_ENV=1`, in which case a missing pair fails closed. The class redacts itself in `repr`/`str`, and the BOM that Windows editors put on the first key is tolerated. The daily runner now uses it. Tests cover precedence, the VM path with no frontend file, partial pairs, and non-disclosure. **Not proven on the VM**: it needs `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` in `backend/.env` or the service environment; credentials must not be committed.

## 7. Proposed `ebay_api_budget_ledger_v2` contract

Keyed by keyset identity (environment plus a hash of the App ID), API name, resource bucket and provider window start. Stored: window end (the provider reset), verified limit, safety reserve, usable limit, requests reserved, last provider usage check, provider-reported used and remaining, usage state, verification time. An atomic `SECURITY DEFINER` reserve RPC (like the V1 one) refuses any reservation beyond `usable_limit` or when verification is missing or stale.

- **Usable limit** = verified provider quota − max(100, 10%): 4,500 of 5,000.
- **Provider analytics** verify the ceiling and the keyset identity only. The **local ledger** does per-request accounting across all hosts.
- **Degraded mode:** if analytics fail, return 204 or error, and the quota was verified within 36 hours and the ledger is healthy, continue under the last verified usable ceiling. If quota identity is unknown, the keyset changed, verification is older than 36 hours, or the ledger is unavailable, fail closed. Analytics failure is never unlimited and never zero.

The decision logic is implemented and tested in `backend/pricing_pipeline/ebay_quota_policy.py` (no schema applied yet). V1's constant and its ledger are unchanged.

## 8. Tests

`backend/tests/unit/pricing_pipeline/test_ebay_quota_and_credentials.py`, 16 tests, all passing with the existing pipeline suite (53 passed, 1 skipped that needs PGlite). Coverage: credential precedence and redaction, the reserve rule, healthy/degraded/fail-closed quota decisions, keyset identity, provider-window handling, separate Browse pools, and 204 handling in the audit normalizer.

## 9. Next action

1. Have an owner decide whether to submit the prepared growth request for Marketplace Insights.
2. Implement `ebay_api_budget_ledger_v2` and its RPC (design above), then move V1's ceiling off the hard-coded 1,000 only through that ledger.
3. Put the eBay credentials in the VM's `backend/.env` or service environment before any scheduled run.
4. Re-read provider usage after a few hours to see whether `buy.browse` catches up with the calls made (expected 8 after this audit); that would settle the getItem attribution.
5. Keep the V1 schedule uninstalled until the host-key and deployment steps from P6Z are resolved.

EBAY_SOLD_ACCESS_DENIED_QUOTA_V2_READY
