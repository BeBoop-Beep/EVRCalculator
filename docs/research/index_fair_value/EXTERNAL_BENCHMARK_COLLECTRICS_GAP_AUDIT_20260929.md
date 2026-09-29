# External Benchmark Gap Audit — Collectrics vs inDex
Date: 2026-09-29

## Purpose

This is a prior-art / competitive benchmark audit, not a replication plan.

The user supplied this reference:
- https://www.youtube.com/watch?v=QjidnOU3CQ0&t=366s

The YouTube transcript was not used as an implementation specification. The audit instead verified the concepts that are publicly exposed in the current Collectrics product and methodology text, then compared those concepts against the current inDex architecture and data authorities.

We should learn from what market questions Collectrics has demonstrated are useful without copying its score names, formulas, UI presentation, thresholds, or inferred-sale methodology.

## Explicit originality boundary

Do not reproduce or clone:

- the HYPE score or its 0-100 presentation;
- the name "Demand Pressure";
- Collectrics' exact sold/active formula or gauge thresholds;
- its 56-day median anchor;
- its "demand -> price timing" presentation;
- its leaderboard ranking formula;
- its "supply saturation shift" formula or naming;
- its labels such as "Cooled", "Elevated", "Extremely hot", "Overhang risk", etc.;
- its blended-price methodology;
- its UI cards, gauges, copy, or visual hierarchy;
- ended-listing inference as a substitute for actual completed-sale evidence where inDex has true sold rows.

What we may legitimately learn from the benchmark is that collectors find several market-microstructure questions useful: current offered supply, fresh supply, transaction velocity, sell-through, price dispersion, grading population, and whether market activity is moving before or after price.

Those are general market concepts, not proprietary expressions.

## What Collectrics publicly exposes

Current public Collectrics card and set pages show a market-flow system with:

### Card-level market state
- blended modeled ungraded price;
- a near-mint proxy;
- PSA 9 / PSA 10 estimates;
- PSA population and gem rate;
- active eBay listings;
- new listings;
- estimated sold listings;
- a sold-to-active demand-pressure style ratio;
- recent change versus a longer baseline;
- unsold-listing / supply-saturation diagnostics;
- daily active-listing snapshots;
- recent eBay listings;
- card-level market-mover rankings.

Its own methodology notes that eBay Browse does not provide actual completed-sale Marketplace Insights data to the product. It instead observes active listings, listing disappearance/ending, listing changes, and periodic checks to build a directionally useful estimate of sales velocity. Collectrics explicitly says this is imperfect and gives eBay a small role in its price model while using it more heavily for market-trend interpretation.

### Set-level market state
Public set pages expose:
- a HYPE score;
- a current demand level relative to a baseline;
- active-listing change;
- new/sold ratio;
- sold/day;
- set-value change;
- a demand-versus-price interpretation;
- a demand-to-price timing history;
- pack rip value and current pack cost.

This demonstrates a coherent market-flow layer, but it combines multiple distinct concepts into a consumer-facing heat / market-state product.

## What inDex already has that is structurally different or stronger

### 1. Actual completed-sale evidence

PkmnPrices provides eBay sold transaction rows. inDex now persists those rows append-only in:
- `pkmnprices_ebay_sold_evidence_v1`;
- `pkmnprices_card_identity_v1`;
- `pkmnprices_sold_sync_state_v1`;
- `pkmnprices_sold_runs_v1`.

This is materially different from estimating sales from ended active listings.

Current vintage evidence already contains 2,702 individual transactions across 12 card identities and reaches as far back as 2024-05-31 for at least one completed backfill. The provider history is cursor-paginated and retained-history dependent rather than a fixed 30-day window.

The broad Fair Value pilot now supports persisting the same raw sold rows it already pays to retrieve.

### 2. Exact physical-variant / edition identity

inDex explicitly models:
- First Edition;
- Unlimited;
- Shadowless;
- printing type;
- special type;
- exact canonical / physical variant identity.

Recent vintage repair work intentionally refused to contaminate scoped markets with generic Holofoil prices.

This identity discipline should also govern all future market-flow metrics.

### 3. Separate intrinsic collector demand

Collector Appeal V7 is intentionally price-blind and excludes:
- market price;
- Treatment;
- Pull Scarcity;
- supply;
- liquidity.

Its supported domains include:
- Pokémon subject appeal;
- Trainer appeal;
- Artist recognition;
- Playability.

This answers a different question from observed marketplace velocity: intrinsic collector interest.

That separation is valuable and should remain.

### 4. Acquisition scarcity

inDex has simulation-derived exact pull probability and expected packs. This measures acquisition scarcity from opening product, not surviving market supply.

This is also intentionally separate from Collector Appeal.

### 5. Treatment / presentation structure

Treatment V3 provides era-local structural categories and semantic card-treatment features.

### 6. Longitudinal TCGplayer market-price authority

inDex retains Near Mint TCGplayer market-price history and compact price-event history. It supports:
- returns;
- volatility;
- drawdown;
- relative set / era behavior;
- persistence;
- historical as-of reconstruction.

It is an aggregate transaction-derived provider estimate, not individual sale detail.

### 7. Active eBay ask evidence already exists

The existing eBay pricing pipeline stores normalized active ask evidence in:
- `ebay_card_listing_evidence_v1`;
- `ebay_pricing_runs_v1`;
- `ebay_card_pricing_run_summary_v1`.

This dataset was originally built as an independent pricing-source research path, but it can support market-supply research if the identity/language contracts are respected.

## The real inDex gaps

The old Fair Value feature inventory correctly identified the major missing domains. PkmnPrices now closes part of one of them.

### Gap A — durable broad completed-sale history
Status: PARTIALLY CLOSED.

We have true sold rows, but only the vintage-gap target set is historically backfilled today.

Needed:
- broad Fair Value cohort identities;
- cursor-exhausted historical backfill;
- daily / incremental persistence;
- stable point-in-time features.

### Gap B — offered-supply history at card/variant grain
Status: DATA EXISTS, RESEARCH AUTHORITY NOT YET FORMED.

We already store active eBay asks, but have not frozen a normalized daily market-supply authority suitable for Fair Value or market-structure research.

Needed:
- exact variant / condition / language eligibility;
- active distinct listing count;
- distinct seller count;
- listing concentration;
- price-depth buckets;
- new-listing flow;
- disappeared / ended listing flow;
- stale listing age;
- seller/listing churn.

### Gap C — market scarcity / surviving supply
Status: MISSING AS A GOVERNED CONSTRUCT.

Pull Scarcity is not market scarcity.

A defensible future Market Scarcity layer should describe how hard a card is to find in the observable secondary market without using price as the definition.

Candidate evidence:
- active eligible listings;
- sellers;
- listing depth;
- sold velocity;
- days between sales;
- listing turnover;
- grading population;
- reprint / supply regime when available.

This is directly relevant to the preregistered research question:
"Does market scarcity predict appreciation after controlling for pull scarcity?"

### Gap D — liquidity / transaction depth
Status: NEW DATA AVAILABLE, NOT YET FROZEN.

Candidate card-level primitives:
- sales in 7 / 30 / 90 / 180 days;
- transaction days;
- median days between sales;
- days since last sale;
- sale-price MAD / IQR;
- low/high spread;
- distinct sold transaction count;
- persistence of transaction activity.

This should be an evidence family, not one synthetic hype score.

### Gap E — condition normalization
Status: OPEN.

Raw PkmnPrices ungraded sales do not provide a structured card-condition field.

Needed:
- deterministic title-condition classifier;
- reviewed precision sample;
- ambiguous/conflicting state;
- temporal TCGplayer NM comparison where valid;
- no automatic ungraded=NM equivalence.

### Gap F — grading / surviving-condition supply
Status: OPEN.

The Fair Value contract correctly says no normalized authority currently exists for:
- PSA population;
- gem rate;
- grading velocity.

This is one area where Collectrics currently exposes useful information that inDex does not yet have normalized.

We should not treat grading population as intrinsic appeal. It belongs in surviving-supply / condition-scarcity research, with strong controls for price-responsive submission bias.

### Gap G — market flow versus price timing
Status: OPEN / FUTURE VALIDATION.

Rather than copying a "demand -> price timing" feature, inDex should ask a stricter research question:

"Do point-in-time market-flow variables predict later excess price movement after controlling for current price trend, Pull Scarcity, Collector Appeal, Treatment, lifecycle, and set/era effects?"

This must be prospective / point-in-time safe.

### Gap H — cross-source market agreement
Status: PARTIALLY AVAILABLE.

inDex can eventually compare:
- TCGplayer Near Mint market estimate;
- condition-normalized eBay sold evidence;
- eligible eBay active asks;
- structural Fair Value;
- market-conditional Fair Value.

This is a distinct opportunity from Collectrics' blended price.

Instead of hiding sources inside one blend, inDex can expose or model **agreement / disagreement** between independently governed sources.

## Recommended original inDex architecture

Do not build one HYPE-like score.

Build separate governed dimensions.

### Domain 1 — Collector Appeal
Question:
"How much intrinsic collector interest does this card represent?"

Existing V7 authority.

Inputs remain price-blind.

### Domain 2 — Pull Scarcity
Question:
"How hard is this card to acquire from sealed product?"

Existing simulation authority.

### Domain 3 — Market Availability
Question:
"How available is this exact card/variant in the observable secondary market?"

Candidate primitives:
- eligible active listings;
- distinct sellers;
- listing concentration;
- listing depth near the current reference range;
- active inventory change;
- listing age / stale supply.

This is the beginning of Market Scarcity.

### Domain 4 — Market Turnover
Question:
"How quickly is available inventory actually clearing?"

Candidate primitives:
- true completed-sale count;
- transaction days;
- sales per active listing;
- median time between sales;
- new supply versus completed sales;
- turnover persistence.

The concept is standard market microstructure; formulas and normalizations must be independently designed and validated.

### Domain 5 — Transaction Quality / Dispersion
Question:
"How consistent are actual clearing prices?"

Candidate primitives:
- median sold price;
- MAD;
- IQR;
- trimmed ranges;
- condition mix;
- sale-type mix;
- outlier rate;
- recency.

This should feed confidence / uncertainty as much as point valuation.

### Domain 6 — Surviving Supply / Condition Scarcity
Question:
"How much collectible-grade supply appears to exist outside sealed acquisition?"

Future candidate inputs:
- PSA total population;
- grade distribution;
- gem rate;
- grading velocity;
- raw-market availability;
- reprint regime.

This must stay distinct from Pull Scarcity.

### Domain 7 — Fair Value
Question:
"What price is structurally consistent with this card's independently governed characteristics and current market context?"

Structural candidate:
- Collector Appeal;
- Pull Scarcity;
- Treatment;
- lifecycle;
- card metadata;
- later: Market Availability / Surviving Supply if independently validated.

Market-conditional candidate:
- all above plus permitted transaction/liquidity context.

Fair Value must never turn into a popularity / hype score.

### Domain 8 — Market State diagnostic
Question:
"What is the market doing right now?"

This can combine descriptive states such as:
- inventory expanding / contracting;
- turnover accelerating / slowing;
- clearing-price dispersion widening / narrowing;
- price moving with or against flow;
- data confidence.

Do not collapse this into Fair Value and do not copy Collectrics' HYPE score or labels.

Potential inDex names should be independently developed after the research stabilizes. For now use neutral internal terms such as:
- Market Availability;
- Market Turnover;
- Market Balance;
- Market State;
- Market Scarcity;
- Transaction Depth.

## Specific advantage inDex can pursue

Collectrics' eBay market-flow system is directionally inferred from daily listing state because it says Marketplace Insights completed-sale access is unavailable.

inDex now has:
1. actual PkmnPrices completed-sale rows;
2. its own active-listing evidence;
3. canonical TCGplayer NM history;
4. exact physical-variant identity;
5. Pull Scarcity;
6. Collector Appeal;
7. Treatment;
8. set/era context.

The research advantage is therefore not "a better demand-pressure score."

It is the ability to ask **causal / controlled separation questions** that a pure marketplace-flow product cannot answer cleanly:

- same Pull Scarcity, different Market Scarcity -> does price differ?
- same Appeal, different turnover -> does price persistence differ?
- same Appeal + Pull Scarcity, different surviving supply -> does Fair Value improve?
- when actual sales accelerate but asks also rise, which signal dominates later price?
- does listing scarcity matter after conditioning on true completed-sales liquidity?
- do Fair Value gaps close differently in liquid versus illiquid cards?
- does condition-normalized sold disagreement carry information beyond yesterday's TCGplayer price?
- does observed Market Scarcity predict future returns after controlling for acquisition scarcity?

These should become preregistered tests, not post-hoc scores.

## Near-term execution order

### Phase 1 — evidence closure
1. Finish broad PkmnPrices sold persistence/backfill.
2. Convert existing active-ask archive into a governed daily offered-supply research table.
3. Keep exact identity and condition/language gates.
4. Build condition classifier research.
5. Audit external grading-population options separately.

### Phase 2 — primitive research
Test independently:
- completed-sale liquidity;
- active offered supply;
- seller concentration;
- transaction dispersion;
- market turnover;
- market scarcity.

Do not combine them until each primitive has clear semantics and stability.

### Phase 3 — controlled Fair Value ablations
Start with current market-anchored baseline.

Incrementally test:
A. liquidity only;
B. supply only;
C. liquidity + supply;
D. condition-normalized price context;
E. surviving-supply / grading inputs.

Use grouped set holdouts and forward-time validation.

### Phase 4 — future Market State product
Only after the primitives prove useful should inDex design a user-facing market-state surface.

It should explain:
- availability;
- turnover;
- transaction consistency;
- price / flow agreement;
- confidence.

It should not reproduce Collectrics' names, formulas, thresholds, or score presentation.

## Current recommendation

Collectrics should accelerate our research prioritization, not define our methodology.

The most important finding from this audit is that inDex's missing piece is not collector demand or acquisition scarcity. Those already have governed systems.

The missing piece is **secondary-market microstructure and surviving supply**.

PkmnPrices sold data plus the existing eBay active-ask archive can now close much of that gap using evidence that is, in several respects, stronger than ended-listing inference.

The highest-value next agent task is therefore:
1. build a governed card/variant/date Market Availability + Market Turnover research dataset from existing sold + ask evidence;
2. keep the components separate;
3. run controlled information-gain and future-return tests;
4. only then decide whether a higher-level Market State construct deserves to exist.
