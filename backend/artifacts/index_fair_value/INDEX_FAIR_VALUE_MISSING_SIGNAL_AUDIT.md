# inDex Fair Value — Missing Signal Audit

As of 2026-09-11, current data cannot support a shippable appraisal model across price bands. The residual pattern is consistent with missing card-level demand, liquidity, and surviving-supply information.

## Authority findings

- [eBay Browse](https://developer.ebay.com/api-docs/buy/api-browse.html) can provide current active listings, prices, conditions, and buying-option distinctions. Browse has a [documented default limit](https://developer.ebay.com/develop/get-started/api-call-limits) of 5,000 calls/day, while production use is subject to Buy API eligibility, licensing, and growth review. It is not a completed-sales authority.
- eBay Marketplace Insights is the highest-interest completed-sales lead, but eBay labels it [Limited Release](https://www.developer.ebay.com/develop/get-started/get-started-on-a-buying-application). No entitlement is present in this repository and access must not be assumed.
- PSA publishes a free, daily-updated [Population Report](https://www.psacard.com/Pop) with totals by grade. Its [public API documentation](https://www.psacard.com/publicapi/documentation) currently lists only single-cert verification. No sanctioned population bulk API, download, or historical snapshot feed was identified; automated collection requires explicit permission.
- The current TCGplayer price authority supplies current/listing-derived price measures, not transaction history. The [audited documented pricing response](https://docs.tcgplayer.com/reference/pricing_getmarketpricebyproductconditionid-1) does not establish seller count, listing depth, sales velocity, or recent transaction count.

## Repository/account audit

No eBay or PSA credential variable names were found in repository environment files. The frontend references `/api/ebaySearch`, but no corresponding server route was found. Therefore no existing eBay Browse, Marketplace Insights, or PSA API entitlement was demonstrated. Secret values were neither printed nor tested.

## Priority

The highest-value signal is matched completed-sale price plus transaction count. It would measure clearing price and liquidity directly and allow time-safe dispersion and velocity features. Because legitimate access is blocked, the practical first pilot is eBay Browse active-listing snapshots after production entitlement, while separately requesting completed-sales access. No scraping of prohibited endpoints and no paid integration are authorized by this study.
