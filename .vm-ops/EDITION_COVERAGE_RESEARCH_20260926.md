# Six unavailable edition markets — source and identity research

## Scope and boundary

Requested by Donny after the Market edition-freshness repair. Research only: bounded read-only SQL, five serial provider catalogue GETs, and offline parser/archive analysis. No business-data writes, migrations, identity changes, runtime deployments, cron changes, or release-gate changes were made. The diagnostic workflows and this report are retained on vm-ops-control; they are not daily schedules.

Database checks ran September 26, 2026, approximately 20:05–20:12 America/Phoenix (September 27 03:05–03:12 UTC). Last SQL clock: 2026-09-27T03:12:03.502306Z. Postmaster remained 2026-09-26T03:47:00.323649Z; not in recovery; no other active queries. Market snapshot remained September 26, updated 02:06:07.998585 UTC, 167 market identities. This is not a fresh certification of separately held Explorer or Set-page workflows.

## Exact stored blockers for September 26

| Market | Priced / expected | Blocking identity or source |
| --- | --- | --- |
| Base 1st Edition | 1 / 102 | Only the existing cross-catalogue Machamp link currently supplies an edition-labelled price. Remaining Base variants have no edition label. |
| Base Unlimited | 0 / 102 | Generic Base catalogue prices exist but are not mapped to this explicit market scope; Machamp also requires a physical-printing exception. |
| Base Shadowless | 0 / 102 | Separate Shadowless commercial catalogue is not connected to the Base canonical checklist/metadata and is not receiving normal current collection. |
| Neo Destiny 1st Edition | 112 / 113 | Shining Noctowl, 110/105: no accepted first-edition variant or price. |
| Neo Revelation 1st Edition | 65 / 66 | Shining Gyarados, 65/64: no accepted first-edition variant or price. |
| Neo Revelation Unlimited | 65 / 66 | Shining Gyarados, 65/64: accepted Unlimited variant exists but no Near Mint raw observation. |

These were checked using get_pokemon_edition_card_prices_as_of_v1 for the requested date and joined to the canonical checklist, not inferred from public labels alone.

## Source capture and reproduction

Production VM runtime SHA: 9e53e6de923cf788da9358e242cd87270a653efb. Runtime parser blob d9ab8e6036ab7acb4ebb5afdabd35c77110d970d matches the inspected main parser.

Read-only provider capture run 36290542811 / job 108539637069 finished successfully at 03:08:35 UTC. It made exactly five serial GET requests to the existing priceguide service, using normal scraper request headers, no retries, and no database client. Every request returned HTTP 200. Captured bodies were run through the pure existing parser without ingestion.

Evidence archive: /home/ubuntu/state/db-safety/edition-coverage-research. Mode 600 files use <group>.<sha256 first 12>.json.

| Group | Catalogue | Response SHA-256 |
| --- | --- | --- |
| 604 | Base Set | 16d5e66f572c635bac886f0bdf7961830e65cb5ea3d1d4b5d3b69d8e4e003e9f |
| 1663 | Base Set (Shadowless) | 6b448cdf4badb1a6e823ad374ff9ea8fb3cdeac7c9092b1fd7c5b2d0d703930c |
| 1444 | Neo Destiny | da6d1f69cc510b71d0abfe641d1170c1b835a87b017c1d402e228c57b0851ede |
| 1389 | Neo Revelation | 0a3c49af3845e764a541087d715ac1c61555b2e240648983dd7bce4b98b8e372 |
| 1840 | Deck Exclusives | 2266bba58637aced47f2ae1dce0719771e8d920102418d633243baa5cd94fc4c |

Offline archive analysis run 36290651736 / job 108539946565 verified those hashes and counted unique checklist positions, source products, printing groups, and Near Mint availability. It used no network or database access.

## Neo: missing source quotes, not an overlooked parser row

### Shining Noctowl

Canonical card: 51507921-0671-4c4d-bdde-84304378ea4a, neo4-110.
Root: 42a3740d-4778-4857-9c28-e116f34b51f3, neoDestiny.
Provider product: 89168.
Accepted Unlimited variant: 5806fb98-edd8-4e56-986d-ceb6b628d3b8.

The captured Neo Destiny guide contains five Noctowl rows: Unlimited Holofoil in five conditions, including Near Mint. It contains ZERO first-edition Noctowl rows in any condition. The pure parser keeps Unlimited Near Mint correctly. That quote is 474.97 in the capture; it must not be copied into the first-edition instrument.

The null-edition placeholder 453293ae-8435-482f-8541-a37461658803 has no raw price history and is marked merged in pokemon_market_explorer_variant_merge_ledger. It is not an undiscovered first-edition instrument and should not be resurrected by relabeling.

### Shining Gyarados

Canonical card: 621b038b-e832-47a2-8bdd-1160945d6d44, neo3-65.
Root: 89e710d1-c378-4b4e-aaea-5994d8441f45, neoRevelation.
Provider product: 89164.
Accepted Unlimited variant: cd756357-1e52-44f9-985d-4ee4b936bc35.

The captured Neo Revelation guide contains four Gyarados rows: Unlimited Holofoil, in Damaged, Heavily Played, Moderately Played, and Lightly Played. There is NO Near Mint row and NO first-edition row. The parser reports its missing-Near-Mint group and rejects it correctly. Its captured 782.55 price is explicitly Lightly Played, not Near Mint.

Raw stored observations for this Unlimited variant contain those played/damaged conditions, with historical dates April 11–August 17, but no Near Mint observations. An explicit legacy link connects the card identity; missing NM coverage is not fixed by adding another identical card link. No external identity row currently exists for this variant.

The other null-edition Gyarados placeholder 6ba0433e-5ba1-47fa-b97e-408266dea0a6 is also marked merged and has no observations. Do not guess it into first edition.

### Implications

Repeatedly running the same guide or lowering the coverage threshold cannot supply the missing edition/condition prices. Identity ingestion should be separable from price ingestion: a verified product/printing should exist even when its quote is unavailable. A missing first-edition identity needs verified external printing/SKU evidence, not inference from an empty price slot.

The remaining pricing dependency is a verifiable English, correct-edition, Near Mint USD observation from an authorized source, or a documented and separately accepted historical-price policy. A listing ask, played-condition price, different edition, or graded-card price is not a substitute for the current TCGplayer NM market-price contract. No suitable accessible replacement quote was certified during this research.

Official TCGplayer documentation describes product SKUs keyed by product, language, printing and condition, and SKU-level market-price requests. Its Getting Started page currently says new API access is not being granted. Therefore a proposal to use that official SKU path is conditional on existing authorized access; it is not a proven free integration available to this account.
References:
- https://docs.tcgplayer.com/reference/catalog_getskusbyproductid
- https://docs.tcgplayer.com/reference/pricing_getproductconditionprices-1
- https://docs.tcgplayer.com/docs/getting-started

## Base: source-catalogue semantics are missing from market identity

### Ordinary Base catalogue

Base root 0010d2ec-894e-4c17-855d-5de6ff6fd204 currently collects group 604 via backend/constants/tcg/pokemon/baseWotcEra/base.py.

The captured group contains 101 products representing 101 unique checklist numbers, all with positive NM quotes. Number 8 (Machamp) is absent. Printing is generic Holofoil (15 cards) or Normal (86 cards), with no explicit edition.

The database has 101 corresponding Base variants with edition=NULL. The parser deliberately records them as MARKET_ONLY_AMBIGUOUS_VARIANT. The corrected edition-history reader correctly refuses to treat an ambiguous variant as proof of a specific edition.

TCGplayer separates the ordinary Base catalogue from Base Set (Shadowless), and its ordinary Base sealed-product descriptions distinguish revised Unlimited from the earlier First Edition and Unlimited Shadowless runs. This supports a narrow, reviewed catalogue/product mapping, not a global rule that NULL means Unlimited.
References:
- https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/base-set
- https://www.tcgplayer.com/product/138130/pokemon-base-set-base-set-booster-pack-revised-unlimited-edition

### The needed other catalogue already exists, but is isolated

Source set d0a3d2ba-c685-4d8c-a5f7-b781b6b730f7, baseSetShadowless, group 1663, is catalog_only=true, has no parent or eligible canonical checklist of its own, and is not attached to Base's exact-scope metadata.

It has 102 commercial card records and 204 variants: 102 labelled raw 1st-edition and 102 raw unlimited. Stored NM observations date only to August 2: 92 first-edition product variants and 100 raw-unlimited product variants have any NM history. These are product counts, not unique checklist-card counts. No current TCGplayer external identity rows were found for these variants.

The live provider catalogue is available. Its contextual meaning matters:
- group 1663 + 1st Edition corresponds to the Base first-edition family;
- group 1663 + Unlimited is the unstamped Shadowless family, NOT the ordinary revised Base Unlimited family;
- group 604 generic printing belongs to the separate ordinary Base catalogue and needs its own approved mapping.

TCGplayer explicitly lists both First Edition and Unlimited products within its Shadowless catalogue. Preserve the provider's raw printing label separately from the canonical physical market scope.
Reference: https://www.tcgplayer.com/search/pokemon/base-set-shadowless?page=1&productLineName=pokemon&productTypeName=Sealed+Products&q=box&setName=base-set-shadowless&view=grid

Do not solve this by making the entire source catalogue a new public root or a counts-toward-parent subset. These are alternate physical editions of the same checklist, not additional cards to sum into every Base basket. Add supplementary collection-source ownership and a canonical variant-level mapping with explicit per-scope membership.

### Existing authority cannot simply accept several legacy links

Live get_pokemon_canonical_card_variant_authority uses DISTINCT ON(canonical_card_id) to choose ONE legacy card before expanding its variants. Explicit cross-catalogue links outrank the existing same-set API identity. Adding another legacy link can therefore replace/hide existing commercial-card variants rather than merge the physical editions.

Repair must support multiple validated commercial product/variant identities per canonical card, keyed by edition scope, without changing the economic identity of unrelated Standard markets. Prefer a narrow explicit variant-level authority with regression tests over a broad global resolution rewrite.

### Machamp and Pikachu require explicit basket rules

Machamp 8/102 is absent from both Base catalogue groups and is supplied by Deck Exclusives group 1840. The current Base checklist link selects ordinary Machamp product 42425, whose variant is stamped 1st Edition. The live provider also has distinct Shadowless Machamp product 107004; BOTH products' printing strings say 1st Edition Holofoil. Their source capture prices differ (27.86 versus 92.51).

Thus a 1st Edition stamp alone does not determine the correct Base physical market family for Machamp. The existing linked ordinary Machamp is the single value currently entering Base first edition; that assignment needs review, not blind reuse. Keep physical-printing/stamp properties separate and define the approved per-market checklist exception. The starter-deck card's checklist eligibility must not automatically make it a booster-pack simulator outcome.

The Shadowless catalogue also contains two number-58 products: Pikachu and Pikachu (Red Cheeks). Its 102 commercial products represent only 101 unique checklist positions. Define a stable per-scope preferred variant or explicitly different basket methodology; do not count both as separate checklist cards or dynamically switch by price.

### Wiring alone cannot provide every fresh NM quote

The frozen live source has:
- Ordinary Base: 101 NM-priced unique checklist positions, missing only separately sourced Machamp.
- Group 1663 First Edition: 89 quoted products but 88 unique checklist positions. Missing positions 1,2,3,4,5,6,7,8,9,11,13,15,16,75. Besides Machamp these are Alakazam, Blastoise, Chansey, Charizard, Clefairy, Gyarados, Hitmonchan, Magneton, Nidoking, Poliwrath, Venusaur, Zapdos and Lass.
- Group 1663 raw Unlimited / physical Shadowless: 98 quoted products but 97 unique checklist positions. Missing Chansey, Charizard, Magneton, Zapdos and separately sourced Machamp.

Historical NM evidence may cover some missing current-day quotes, but must retain its original observation date and verified exact printing. Full historical/current reconciliation was not promoted as a certified basket. Base Unlimited is the strongest first recovery candidate after catalogue normalization and correct Machamp membership; all six cannot honestly be promised certified from this priceguide alone.

## Component price age is a distinct issue

As-of September 26, the new edition reader uses valid historical prices where no newer quote exists:
- Neo Destiny first edition: 112 priced positions, only 98 observed on September 26; oldest used date April 24.
- Neo Destiny Unlimited: 113 priced, 109 observed September 26; oldest July 26.
- Neo Revelation first edition: 65 priced, 60 observed September 26; oldest June 3.
- Neo Revelation Unlimited: 65 priced, 64 observed September 26; oldest August 11.

An aggregate valuation date is not a promise that every component quote was refreshed that day. Preserve this distinction in diagnostics and public coverage/age labels; a new snapshot timestamp must never be used to relabel old observations.

## Recommended implementation order and acceptance tests

1. Implement a reviewed provider catalogue + product + printing -> canonical variant/scope mapping, supplementary Base source ownership, and explicit Machamp/Pikachu roster rules. Test entirely offline using the captured responses first. Recover Base Unlimited before broad backfill because it has 101 live NM positions plus a separately available Machamp product, subject to the approved roster exception.
2. Connect and collect Base's missing source catalogues through the existing guarded queue, without promoting the source catalogues into duplicate public roots. Reconcile existing legacy IDs/external identities and any valid historical observations; preserve raw records and prohibit cross-edition borrowing. Resolve current source-date dependencies for supplementary inputs, not only the primary Base job.
3. Bootstrap the verified missing Neo variant identities separately from pricing, and add bounded targeted exact-NM quote retrieval for uncovered positions. Validate authorized source access and data contract before promising availability or buying a provider. Keep unresolved prices unavailable; optionally expose a clearly labelled priced portion rather than a falsely complete set value, without weakening the certified-value contract.
4. Run V2 projection, edition metadata/history rebuild, and public readback only for affected roots/dates, one stage at a time under existing coordination. Backfill only dates supported by original evidence. Invalidate refresh receipts/prepared outputs using identity/roster/source-policy fingerprints as well as scrape completion so mapping corrections are not skipped as already-current.
5. Regression checks: no edition cross-contamination; all expected canonical IDs appear exactly once; product variants do not collapse; Machamp assignments are explicit; Pikachu is not double-counted; missing NM is never replaced with LP; valid older quotes retain dates; paginated reads are complete; all published certified entries match their correct-date history. Verify a subsequent scheduled cycle maintains the corrected mapping and does not reopen the old bulk cron dependency.

The existing 15 certified edition markets and the recovered Market feed should remain undisturbed while this additional work is validated. These mapping, quote-sourcing, and coverage changes are NOT yet implemented by this research pass.
