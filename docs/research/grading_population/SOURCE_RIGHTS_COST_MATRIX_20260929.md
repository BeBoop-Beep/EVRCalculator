# Grading population and graded-price source matrix

Date researched: 2026-09-29

This is a current public-document audit, not permission to scrape or redistribute.
“Not publicly documented” means the public sources reviewed did not establish the
capability or right. Population always means **observed graded population / submissions
represented by the grading service**, never copies in existence.

## Population sources

| Source | Current population and grade detail | History | Cadence | Export / API | Access, rights and cost |
| --- | --- | --- | --- | --- | --- |
| PSA Population Report | Free searchable current report. Whole grades 1–10/Auth, half grades 1.5–8.5, and qualified grades are separate lines. PSA warns that late-recognized varieties can make counts incomplete. | No official historical series found publicly. | PSA’s Set Registry glossary says population is updated daily. | No report export found. PSA has an authenticated public REST API, but its current public documentation says available methods are single-cert verification—not population. | Population report is publicly viewable. Bulk storage/redistribution rights were not found. Do not automate without separate permission. |
| CGC Cards Population Report | Official current report covers every card type certified by CGC and supports game/era/set and language navigation. The report describes counts by card/grade and expressly says population is informational, not an indicator of value or rarity. | No official history endpoint/export found publicly. | Not publicly documented. | No public population API/export found. The report may redirect through Collectibles Group login in some sessions. | Use free report for manual validation only; no bypass of login or access controls. Storage/redistribution rights not publicly documented. |
| Beckett/BGS Population Report | Report pages expose copies graded, higher/lower counts, first/last graded and grade selection when available. | No official longitudinal export found publicly. | Not publicly documented. | No public population API/export found. Search results can require login or Online Price Guide subscription. | Beckett’s platform was in maintenance during this audit; its official maintenance page says population/price tools may be temporarily unavailable and active OPG subscriptions were extended. Use only legitimate account access for spot checks; no protected scraping. |
| GemRate public site | Free web search, set breakdowns, universal sets and trend reports; Partner page advertises unified PSA, Beckett, SGC and CGC data. | Public browsing is not a governed machine-readable history authority. | Partner page says daily. | Public Partner demo exposes cert, population and structured-search concepts; API key required for production API. | Public website terms reserve service content/IP. They do not grant the storage, derived-display or redistribution rights this program needs. |
| GemRate Partner API | Current card population includes per-grader totals, grade distributions, qualifiers, gem totals/rates, grader IDs/spec IDs and source dates. Grader-native label keys preserve half grades and special tens. | Daily population history begins 2022-01-01, but history is not included in basic plans. | Daily; history documentation says once daily. | Structured search, stable grader/universal IDs, spec lookup, population endpoint; gated change feed and bulk Pokémon catalog. Numeric rate limits are not public; docs define HTTP 429 only. | Commercial price is not public. History, change feed and catalog require entitlement. Contract terms for retention, derived analytics, public display, attribution and raw redistribution are not public. Procurement required before ingestion. |

Official evidence:

- [PSA Population Report](https://www.psacard.com/Pop/Search)
- [PSA daily population definition](https://www.psacard.com/psasetregistry/glossary)
- [PSA Public API documentation](https://www.psacard.com/publicapi/documentation)
- [CGC Cards Population Report](https://www.cgcgrading.com/cards/population-report/)
- [CGC population-report FAQ](https://www.cgccards.com/about/help-center-faqs/cgc-cards-website/cgc-cards-pop-report/)
- [Beckett Population Report](https://www.beckett.com/grading/set_match/30728980)
- [Beckett current maintenance/access notice](https://maintenance.beckett.com/)
- [GemRate Partner API](https://www.gemrate.com/partner)
- [GemRate API introduction](https://docs.gemrate.com/introduction)
- [GemRate population history](https://docs.gemrate.com/api-reference/cards/get-population-history-for-a-card)
- [GemRate change feed](https://docs.gemrate.com/api-reference/cards/population-change-feed)
- [GemRate catalog](https://docs.gemrate.com/api-reference/catalogs/download-a-catalog)
- [GemRate ID semantics](https://docs.gemrate.com/gemrate-id)
- [GemRate grade labels](https://docs.gemrate.com/gemrate-grades)
- [GemRate public website terms](https://www.gemrate.com/terms)

## Graded-price evidence (kept separate)

| Source | Role | Current public capability | Decision |
| --- | --- | --- | --- |
| PkmnPrices individual graded completed sales | Primary machine-readable graded transaction evidence | Existing inDex client/persistence contract preserves grader, grade and qualifier. | Primary research ledger. A transaction is evidence, not canonical graded price. |
| PSA Auction Prices Realized | Free manual validation | PSA says 5M+ realized results from eBay, Goldin and others, updated daily. | Manual spot validation; not population authority. |
| PSA Price Guide | Free manual benchmark | Official PSA-certified price guide, updated regularly and informed by price histories/public auctions. PSA cautions low-pop cards can command premiums not reflected by general guide values. | Secondary spot check; not transaction or population authority. |
| Card Ladder Free | Free manual benchmark | Free price-guide search and daily sales recap; all-time sales history and full population reports are not in free tier. | Manual spot validation only; do not scrape. |
| Card Ladder Pro | Optional later benchmark | Official pricing is $20/month or $200/year; Pro adds all-time sales history and full population reports/growth. | Do not subscribe now. Consider one month only after a named independent-price validation gap and a manual evaluation plan exist. |

Price-source evidence:

- [PSA Auction Prices Realized](https://www.psacard.com/auctionprices)
- [PSA Price Guide](https://www.psacard.com/priceguide)
- [Card Ladder pricing/features](https://cardladder.com/pricing)
- [Card Ladder methodology overview](https://www.cardladder.com/why-card-ladder)

## Free-versus-paid recommendation

Recommendation: **NEED_MORE_INFORMATION**.

Official sources are sufficient for semantics and manual spot validation, but not for a
normalized cross-grader historical authority. GemRate appears technically suitable, yet
price, limits and the necessary data rights are unresolved. Do not pay merely for
convenience and do not ingest live data until the procurement questions are answered in
writing. Card Ladder Pro and PriceCharting are not recommended for purchase in this bucket.
