# inDex eBay D2 — Listing Identity Benchmark

## Outcome

The evidence-preparation stage is complete, but authority acceptance is blocked by the required independent human review. The repository now contains a frozen, blinded 1,050-row queue spanning all 70 D1 cards. All `gold_label` fields remain empty and all rows are marked `PENDING_INDEPENDENT_HUMAN_REVIEW`.

No D2 matcher was tuned, no D1/D2 performance metric was invented, and no Fair Value model or recurring collector was created.

## Payload audit

The fresh capture observed 6,644 listings. Title, item ID, condition, buying options, seller, image URL, and item URL were populated for 100%; condition ID for 99.97%; price for 95.74%; and shipping options for 96.70%. Category ID, localized aspects, and brand were absent from these search summaries. Card name, number, set, rarity, year, game, language, grader, grade, and certification are therefore not dependable structured fields in this payload and must be derived cautiously from title or obtained through a separately approved detail call.

## Gold-set integrity

The queue was frozen before any D2 revision and omits the D1 prediction column. It samples within every card and provisional D1 state, including retained, ambiguous, rejected, graded, lot, non-English, accessory, and sealed cases. Matcher output is explicitly not ground truth.

Required next action is independent review using the frozen taxonomy, followed by a blind re-review of every false positive, every high-dollar false negative, at least 50 accepted records, and at least 50 ambiguous/rejected records. Disagreements require adjudication and must be reported.

## Pre-registered gate

Only `EXACT_HIGH_CONFIDENCE` may enter an initial authority. It must achieve at least 99% precision with a Wilson 95% lower bound of at least 98%, at least 80% card-level usable coverage, and zero accepted catastrophic wrong-card, graded, non-English, lot/bundle, sealed/accessory, or unresolved-variant cases. These thresholds are frozen before labels and will not be weakened.

## Authority split

`EBAY_ACTIVE_SUPPLY` and `EBAY_ASKING_PRICE_DISTRIBUTION` must be separate. Complete supply counts require validated identity and pagination through returned `next` links. A bounded asking-price sample may eventually be sufficient if identity and distribution stability pass. Browse `total` remains diagnostic only.

## Access follow-up

The current application can call Browse, but no demonstrated Marketplace Insights entitlement exists. The current official Marketplace Insights documentation redirects to a private sign-in surface, and no concrete application path for this account was confirmed. Status: `LIMITED_RELEASE_NO_PATH_CONFIRMED`.

## Decision

- `EBAY_ACTIVE_SUPPLY_AUTHORITY_NOT_READY`
- `EBAY_ASKING_PRICE_AUTHORITY_NOT_READY`
- `EBAY_FAIR_VALUE_SIGNAL_NOT_READY`

D3 and Fair Value F2D must not begin until the independent benchmark and frozen acceptance gate pass.
