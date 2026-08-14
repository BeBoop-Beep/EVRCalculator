# Browser Performance — Rankings, Market, Home

Companion to `PERFORMANCE_HOME_MARKET_AUDIT.md`, which covers the server/publication side.
This document covers the **browser** side and the Rankings client-boundary projection.

Branch `feature/perf_updates_two`, starting SHA `ca2b4e101c92369388798922bb7a293330b12525`.
Backend local against live Supabase. Publication verified current and slim before measuring:
publicationId `8fd439ac-…`, marketDate `2026-08-13`, 1,512,908 B, V4/V5/V6 and
`financial_rip_v3_payload` absent 0/34, `payload_guarantees_canonical_set_value` **True**,
Set Value compatibility enrichment **skipped**.

---

## User-observed local cold load

Reported: `/Market` ~3–4 s, `/Rankings` roughly 2× that. Both observations were made against a
**local dev server**, so dev compilation and production behaviour are separated below.

---

## Dev compile decomposition

Measured on an isolated dev server (port 3200, own dist dir) so the user's own dev server on :3000 was
never touched. Each page got a **fresh** dev server whose first compiled route was that page.

| Page | load 1 (first touch) | load 2 | load 3 | route compile | modules | HTML bytes (compiled) |
|---|---|---|---|---|---|---|
| `/Rankings` | **3.97 s** | 0.212 s | 0.276 s | 2.9 s | 773 | 1,358,768 |
| `/Market` | **3.16 s** | 0.116 s | 0.121 s | 2.2 s | 778 | 245,101 |
| `/` | **7.51 s** | 0.107 s | 0.123 s | 6.1 s | 1,851 | 200,129 |

**Dev compilation does not explain a 2× Rankings-vs-Market gap.** Server-side first touch differs by
only ~0.8 s (3.97 vs 3.16), and the homepage — which the user did not flag — is the slowest to
compile at 7.5 s. What separates Rankings from Market in dev is the **document**: 1,358,768 vs
245,101 bytes, a 5.5× difference the browser must transfer, parse as RSC flight data, and hydrate.

Conclusion: the user's ~2× was **not** dev compilation. It was the Rankings client-boundary payload,
which is a production problem too — and is what this pass fixes.

---

## Rankings client-boundary payload

`app/Explore/page.js` (served at `/Rankings`) passed `leaderboardTargets` — **complete canonical
targets** — into `ExploreTableClient`, which is `"use client"`. Every property of every target was
therefore serialized into the RSC flight payload and shipped to the browser.

Measured on the current cohort (22 eligible targets after the public-coverage filter):

| | bytes |
|---|---|
| Full client-boundary targets | 1,118,440 |
| Projected client-boundary targets | **41,141** |
| Saved | 1,077,299 (**−96.32%**) |

For comparison, `/Market`'s projection is 16,877 B over 34 targets. Rankings stays larger **per
target** because its contract is genuinely wider: seven sortable columns, 1D rank movement for two
metrics, and eight ranking modes, versus the ladder's 12 scalar fields.

---

## Rankings consumer contract

Traced through `ExploreTableClient`, `exploreRankingConfig`, `rankingsSort`, `SetIdentity`,
`rankingMovement`, `canonicalRipV7` and `ripStatisticsRouting` — by following helper functions that
receive whole target objects, not by text search alone. 74 projected paths.

| Family | Fields | Class |
|---|---|---|
| Identity / routing | `target_type`, `target_id`, `set_id`, `id`, `name`, `era`, `logo_image_url`, `symbol_image_url` | CURRENT_VISIBLE_REQUIRED |
| Sortable columns | `mean_value` (EV), `pack_cost` (Market Pack Price), `prob_profit` (Chance to Beat Cost), `expected_loss_when_losing` + `expectedLossWhenLosing` (Average Loss) | CURRENT_VISIBLE_REQUIRED |
| Overall RIP | `overallRipV7.{relativeScore,rank,cohortSize,tier}` | CURRENT_VISIBLE_REQUIRED |
| Financial RIP | `financialRipV3.{relativeScore,rank,cohortSize,tier}` | CURRENT_VISIBLE_REQUIRED |
| Collector Appeal | `publicRipContractV7.collectorAppeal.*` (only source — no top-level V3 appeal block exists) | CURRENT_VISIBLE_REQUIRED |
| Canonical contract siblings | `publicRipContractV7.overallRip.*`, `.financialRip.*` | CURRENT_VISIBLE_REQUIRED (see note) |
| 1D rank movement | `previousOverallRipRank1d`, `overallRipRankComparisonStatus1d`, `previousFinancialRipRank1d`, `financialRipRankComparisonStatus1d` (+ snake_case) | CURRENT_VISIBLE_REQUIRED |
| Set Desirability mode | `universalSetDesirability.{score,rank,rankedSetCount}` | CURRENT_HIDDEN_BUT_SUPPORTED |
| Experience / Chase / EV-vs-cost / Biggest Upside / Jackpot Upside modes | `relative_experience_score`,`experience_rank`,`experience_tier`, `relative_chase_potential_score`,`chase_potential_rank`,`chase_potential_tier`, `mean_value_to_cost_{ratio,rank,tier}`, `relative_biggest_upside_score`,`biggest_upside_{rank,tier}`, `p99_value_to_cost_{ratio,rank,tier}` | CURRENT_HIDDEN_BUT_SUPPORTED |
| `publicRipContractV7.audit` | — | LEGACY_UNUSED — dropped |
| `openingExperience`, `rip`, `ripCore`, `overallRipV5/V6`, `rip_core_interpretation*`, `desirabilityCoverage`, … | — | LEGACY_UNUSED — dropped |

**Hidden modes are retained deliberately.** `RANKING_MODE_PICKER_ENABLED` is false, but
`exploreRankingConfig.mjs` states the alternative lenses are kept for future paid functionality.
Dropping their fields would turn a hidden feature into a silently broken one the moment the flag
flips — every score would read `null` and render "Unavailable".

**Note on contract siblings:** `resolveCanonicalRipV7` prefers `publicRipContractV7` whenever it has
*any* content and then reads `overallRip`/`financialRip` from it. Shipping a contract containing only
`collectorAppeal` would hand any resolver caller an empty Overall RIP, so all three blocks are kept
and only `audit` is dropped.

---

## Rankings projection

`lib/explore/rankingsClientProjection.mjs`. Eligibility filtering and the canonical rank sort still
run on the **complete** targets; only what crosses into `ExploreTableClient` is projected.

**This is a server→client (RSC) optimization only.** It does not narrow the backend fetch —
`getRipStatisticsTargets` still reads the full canonical cohort, deliberately, because that is the
shared cache identity Rankings, `/Market` and set detail reuse.

---

## Browser before/after — isolated production build

Two builds (`.next-perf-before`, `.next-perf-after`) differing **only** in whether the projection is
applied. 20 server requests + 10 browser runs per page, same window, same publication. Times in ms,
bytes in B.

### /Rankings

| Metric | BEFORE p50 | AFTER p50 | Δ |
|---|---|---|---|
| TTFB | 41.7 | **10.2** | −76% |
| FCP | 176 | **56** | −68% |
| LCP | 288 | 252 | −13% |
| TBT | 8 | 0 | −8 ms |
| CLS (×1000) | 5.4 | 0 | — |
| DOMContentLoaded | 143.2 | **53.7** | −62% |
| load | 227.7 | **110.5** | −51% |
| document, gzip | 186,011 | **19,638** | **−89.4%** |
| document, decoded | 1,343,751 | **174,712** | **−87.0%** |
| total transfer | 2,712,019 | **1,538,899** | −43% |
| JS bytes | 890,644 | 890,644 | unchanged |
| image bytes | 303,849 | 303,849 | unchanged |

### /Market (control — unchanged this pass)

| Metric | BEFORE p50 | AFTER p50 |
|---|---|---|
| TTFB | 11.9 | 11.8 |
| FCP | 56 | 56 |
| LCP | 244 | 268 |
| document gzip / decoded | 24,252 / 219,561 | 24,254 / 219,561 |
| total transfer | 1,727,651 | 1,723,001 |

### / (control — unchanged this pass)

| Metric | BEFORE p50 | AFTER p50 |
|---|---|---|
| TTFB | 8.6 | 8.9 |
| FCP | 48 | 48 |
| LCP | 168 | 168 |
| document gzip / decoded | 21,839 / 106,667 | 21,840 / 106,667 |
| total transfer | 1,283,505 | 1,283,505 |

Market and Home moving by less than run-to-run noise is the control that validates the Rankings
deltas as real rather than environmental.

---

## Three-page comparison (production, warm, AFTER)

| Metric | Rankings | Market | Home |
|---|---|---|---|
| TTFB p50 | 10.2 | 11.8 | 8.9 |
| FCP p50 | 56 | 56 | 48 |
| LCP p50 | 252 | 268 | 168 |
| TBT p50 | 0 | 0 | 0 |
| doc gzip | 19,638 | 24,254 | 21,840 |
| doc decoded (≈RSC) | 174,712 | 219,561 | 106,667 |
| JS bytes | 890,644 | 887,600 | 847,110 |
| image bytes | 303,849 | 446,395 | 126,880 |
| total transfer | 1,538,899 | 1,723,001 | 1,283,505 |
| LCP element | `IMG.set-page-atmosphere-bloom` | `IMG.set-page-atmosphere-bloom` | `H1` |

After the projection the three pages are within ~20% of each other on every browser metric. Rankings
is no longer the outlier — it now has the **smallest** document of the three.

---

## Functional parity

Two independent proofs, both zero-difference.

**1. Selector-level equivalence harness** — the real consumers run over full vs projected targets:
`rankTargets` order; all 8 ranking modes × {score, rank, tier, cohort size, formatted score}; all 7
sortable columns × {ascending, descending} full orderings **and** per-row sort values; Collector
Appeal blocks; Average Loss; identity fields; 1D movement for both metrics; eligibility.
**0 differences.**

**2. Real-browser UI parity** — the rendered `/Rankings` page on both builds: default order, then every
header clicked twice (20 sort states), comparing row text, `href`s, image `src`s, `aria-sort` and full
page text. 23 table rows, 10 headers. **0 differences.**

---

## LCP / main-thread findings

Rankings' LCP element in production is `IMG.set-page-atmosphere-bloom` — the **ambient background
artwork**, not table text. Same for `/Market`. The homepage's LCP is its `H1`.

TBT is ~0 on all three pages after the change, and JS bytes are unchanged (890 KB Rankings / 888 KB
Market / 847 KB Home) — the projection removed RSC payload, not JavaScript. So main-thread scripting
is **not** currently the constraint on any of the three pages.

Rankings LCP improved only 288 → 252 ms because it is gated by a background image, not by the
document. That image is now the single largest remaining lever on Rankings and Market LCP, and it is
decorative (`hidden desk:block`, `loading="lazy"`). Not touched in this pass — no change was made on
speculation.

---

## Remaining priorities

1. **Ambient background artwork is the LCP element on both Rankings and Market.** It is decorative and
   lazy-loaded yet still wins LCP. Worth investigating whether it should be excluded from LCP
   candidacy or downsized — but measure before changing.
2. **JS bundle ~890 KB** on all three pages, First Load JS 102 KB shared. TBT is 0 today, so this is
   not urgent.
3. **Image bytes on /Market (446 KB)** — the largest image payload of the three.
4. Server-side items remain as recorded in `PERFORMANCE_HOME_MARKET_AUDIT.md` (shared Home/Market
   summary projection; narrower `/insights/secondary`).
