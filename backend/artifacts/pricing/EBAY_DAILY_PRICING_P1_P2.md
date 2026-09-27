# eBay daily pricing P1/P2

Market date: 2026-09-19. Workspace: `D:\EVRCalculator`, branch `develop`.

## Reused architecture

The existing shadow Browse collector retains its deterministic two-query strategy, three-page maximum, bounded retries, raw JSONL capture, matcher output, and checkpoint/resume state. The pricing planner reads canonical cards, sets, and the current TCGplayer canonical price view. It writes only a local JSON manifest. The collector writes only local JSONL and checkpoint files. No pricing database table is written.

## Target selection contract

Only approved main canonical cards with a set and usable card identity enter the candidate set. Missing Common, Uncommon, Promo, or Energy cards are not promoted merely for a gap. A candidate needs high rarity, a current price of at least $20, or opening eligibility with rarity above those ordinary categories. All applicable reasons are retained. Important gaps, stale TCGplayer prices (14 days), high value ($50), and high rarity are prioritized; 20% of planned calls are reserved for date-seeded rotation among otherwise eligible candidates. The hash of market date and canonical ID makes rotation reproducible. A duplicate canonical ID raises an error.

The selector computes each target's exact frozen query formulations via `generate_queries`, then budgets three possible pages per query. This is a worst-case planned cost, not an observed call count. The 900-call ceiling leaves 100 of the 1000 application calls for retries and operational variance. The pricing CLI also caps a run at its manifest ceiling. Operators must coordinate multiple runs on the same date; the existing collector has a per-run counter, not a cross-run eBay usage ledger.

## Real database dry run

Manifest: [ebay_daily_pricing_targets_2026-09-19.json](ebay_daily_pricing_targets_2026-09-19.json). It contains target IDs, resolved variant IDs, prices and capture timestamps, set, era, rarity, reasons, planned queries, per-target cost, and selector fingerprint `01dd1027a3d4afc0586f4f687105a39e39877bbd3e6f43208fd01f57fdffcc63`.

| Measure | Count |
| --- | ---: |
| Eligible candidates | 8,509 |
| Targets | 150 |
| Planned requests | 900 |
| Sets / eras | 59 / 15 |
| Missing-price targets | 60 |
| Rotation targets | 30 |
| Important price gap | 60 |
| Stale TCGplayer price | 120 |
| High value | 45 |
| High rarity chase | 105 |
| Opening EV input | 135 |
| Set Value input | 150 |

Reasons overlap. The CLI dry run resolved all 150 planned targets and made zero eBay calls.

## Collector and English eligibility

Raw `active_ask` rows retain item, target and variant IDs, title, condition, item and shipping prices, seller, URLs, query formulation, timestamp, run ID, and raw response. `landed_ask_value` is set only when item and shipping values are known in the same currency; it is otherwise null. This is an ask, never a sale.

Pricing match rows use the existing D3-v5 exact-card identity classifier. Only `HIGH_CONFIDENCE` is identity-qualified. Structured `Language` metadata is evaluated using the existing language-v1 policy: explicit English gives `ENGLISH_ELIGIBLE`, explicit non-English gives `NON_ENGLISH_EXCLUDED`, and absent or unrecognized metadata gives `LANGUAGE_UNRESOLVED`. Failed identity gives `IDENTITY_REJECTED`. Browse search summaries normally lack `localizedAspects`, so a search-only run will usually produce unresolved language; it cannot safely produce an English price pool without item detail or other authoritative language evidence. The raw rows remain available regardless of match status. The CLI reports raw, identity-qualified, English-eligible, unresolved, and rejected counts separately.

No live Browse request was made for this P1/P2 validation. Actual evidence counts are therefore zero; the dry run is a plan, not a capture. A bounded live run is available with `--live-smoke --target-file <manifest>` and a full artifact run with `--run --target-file <manifest>`.

## Verification and next contract

Focused tests: 23 passed. They cover priority order, missing and stale prices, recent movement, ordinary missing card exclusion, rotation, budget, no duplicate targets, active-ask and landed-price semantics, language states, identity rejection, and collector resume. The source path contains no insert/upsert/update/delete call to pricing tables. Existing TCGplayer current-price authority is unchanged.

P3 should add an explicit item-detail language-enrichment budget and a durable daily application-call ledger before production scheduling; keep language-unresolved asks outside the English price pool. It should define idempotent raw observation persistence, target/listing provenance, source separation from TCGplayer, and publication gates. This planner recognizes 20%/$5 movers and 30%/$5 volatility from price-event history, but its live history read is capped at the newest 1,000 TCGplayer events in a 30-day window. That sample was full on this run and produced no selected mover or volatility targets. A complete historical ranking needs a bounded indexed aggregate or materialized signal; the current sample cannot claim exhaustive movement coverage.

EBAY_DAILY_PRICING_TARGETING_AND_COLLECTOR_READY_FOR_DB_PERSISTENCE
