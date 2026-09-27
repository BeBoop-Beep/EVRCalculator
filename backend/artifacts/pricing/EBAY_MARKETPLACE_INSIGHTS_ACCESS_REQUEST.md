# eBay Marketplace Insights access request (draft, NOT submitted)

**Status: draft for the account owner. Nothing here has been sent to eBay.** Submit it yourself through the developer account's Application Growth Check or support workflow. I could not re-verify eBay's current submission form or process from this environment (eBay's developer pages returned HTTP 403 to my fetcher), so confirm the correct channel and any required fields when you submit. Bracketed items are only known to the account owner.

## Summary

- **Application:** [APPLICATION NAME], production keyset, App ID [PASTE FROM DEVELOPER ACCOUNT], developer account [ACCOUNT NAME/EMAIL].
- **Requested:** access to the **Marketplace Insights API** (`buy.marketplace.insights` scope; item sales search), marketplace **EBAY_US**. If it is available in the same approval, also `getItems` (Browse bulk) for the same use.
- **Current evidence that access is missing (2026-09-21, production keyset):**
  - OAuth client-credentials request with scope `https://api.ebay.com/oauth/api_scope/buy.marketplace.insights` returned **HTTP 400 `invalid_scope`**.
  - `GET /buy/marketplace_insights/v1_beta/item_sales/search?q=pokemon card&limit=1` with the standard application token returned **HTTP 403, errorId 1100, "Access denied"**.
  - `GET /buy/browse/v1/item?item_ids=…` (getItems) returned **HTTP 403, errorId 1100**.
  - The Developer Analytics rate-limit response lists a `buy.marketplaceinsight` bucket of 5,000/day for the app, but listing a bucket did not grant access.

## Application purpose

A Pokémon trading-card market-data service. It tracks the price of **English** single cards, in **Near Mint-compatible** condition, to support current-price and valuation analysis for collectors. The service is read-only market analysis: **no automated purchasing, bidding, listing, or messaging of any kind.**

## Current approved usage

- Browse API item search (`/buy/browse/v1/item_summary/search`), category-filtered, shallow (small limit).
- Browse API item detail (`/buy/browse/v1/item/{id}`) for a small number of promising candidates per card.
- Application token only (client-credentials). No user data or user tokens.
- Measured production usage: the production pipeline made **150 requests for 21 cards** in its first run (about 7.1 requests per card, zero failures, zero retries), and an earlier 120-card study used 836 requests. Real provider quota is 5,000/day per Browse bucket; the pipeline plans to use at most **4,500 (90%)** and normally about 3,600.

## Why completed-sales access is needed

Active asking prices measure what sellers *hope* to receive; they systematically differ from what buyers pay, and in our data the gap depends on price level and shipping. In a 25-card paired study, the active-ask estimate was a median of about 16% above the reference price overall, about 50% above below $5, and about 8% above at $20 and up, with three severe disagreements, all on cards under $5. We cannot tell whether that premium is real seller optimism or reference-price lag without realized clearing prices. Completed sales are required to:

- measure realized prices for the same exact physical card;
- compare sold versus asking prices to quantify market quality and the ask premium by price level;
- avoid guessing sales from listings that disappear (we do not do this and will not).

## Data needed

Per completed sale of a targeted card: sold price and currency; sold date/time; item identity (item ID, title, image URL) sufficient for exact physical-card matching; condition (and descriptors where available); shipping cost if available; buying format; quantity sold if available; whether a Best Offer transaction price is represented (if not, we will exclude Best Offer sales rather than guess). Seller usernames are not needed; we store a one-way hash of any seller identifier only.

## Expected volume (realistic, not inflated)

- **Targets:** the same daily card set as the active-ask pipeline: about **500 cards/day** at full V2 capacity, prioritized (missing-price gaps, high-impact cards, disagreement refreshes, stale prices, movers, rotation).
- **Marketplace Insights calls:** about **1 search per targeted card per day**, plus at most one follow-up page for cards with many results: roughly **500–1,000 calls/day**, well inside the 5,000/day bucket the app already shows. Retries are bounded (a few attempts per request, all counted).
- We would start smaller (about 100 cards/day) to validate efficiency before scaling.

## Efficiency and controls

- **Adaptive targeting:** cards are prioritized by economic importance; unresolvable identities are never queried.
- **Shallow requests:** small page sizes, category-filtered, and we stop as soon as a card has sufficient evidence (for active asks: five distinct sellers).
- **Idempotency and caching:** a completed day is never re-fetched; a resumed run skips finished cards.
- **Quota guard:** a database ledger reserves every request atomically across all hosts before it is sent, keyed to the provider's own reported rate-limit window and resource bucket, with a 10% safety reserve (never 100% of quota), and it fails closed if the quota cannot be verified. Provider usage analytics are used to verify the limit, not to exceed it.
- **Bulk requests** (`getItems`) will be used where supported once available, to reduce call counts.

## Data safety and privacy

- Server-side storage in a managed database with row-level security and no public access; only the service backend can read or write it.
- Minimum retained provider payload: normalized fields needed for pricing provenance are stored; full raw responses stay on the operations host only and are not published.
- No credentials in code, artifacts or logs; secrets live in the environment/config of the backend service.
- Exact provenance per record (listing/sale ID, capture time, policy version, fingerprints) so every price can be traced and reproduced.
- Seller and buyer personal data are not collected or exposed; nothing from eBay is redisplayed publicly as raw listing or sale records. Any public output would be derived aggregate price statistics.
- We will comply with the eBay API License Agreement and Data Handling requirements, including data deletion and retention limits eBay specifies for this API. [ACCOUNT OWNER: confirm the specific retention limits that apply to Marketplace Insights data.]

## Contact

[NAME] — [EMAIL] — [BUSINESS/PROJECT DESCRIPTION AND URL, IF ANY]
