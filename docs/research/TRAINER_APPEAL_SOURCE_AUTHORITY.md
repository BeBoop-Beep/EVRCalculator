# Trainer Appeal Source Authority Research

**Status:** `TRAINER_APPEAL_SOURCE_AUTHORITY_SUPPORTED_WITH_LIMITATIONS`  
**Scope:** research only; no scoring or publication changes  
**Primary current source:** Google Trends Trainer search-interest captures  
**Decision date:** 2026-09-09

## 1. Decision

Trainer Appeal does **not** need to be built from the same source families or on the same raw evidence scale as Pokémon Appeal.

Trainer, Pokémon, Artist, Functional, and future collectible dimensions are intentionally separate evidence buckets. The correct source question is therefore:

> Is the Trainer-specific evidence internally coherent, broad enough, reproducible enough, and identity-safe enough to support a Trainer Appeal authority inside the Trainer bucket?

For the current project, the answer is **yes, with disclosed limitations**.

Google Trends is sufficient to serve as the current Trainer Appeal evidence authority. Additional direct-preference polls, official Pokémon polls, Wikimedia, or future sources may strengthen or validate the Trainer bucket later, but they are **not blockers** to moving forward.

This research does **not** select or change the final Trainer scoring formula. It assesses whether the existing evidence is sufficient to support that later scoring decision.

## 2. Existing source authority

The current successful Trainer source runs are both `google_trends_trainer`, captured through the same versioned ingestion path:

- 12-month window: `today 12-m`
- 5-year window: `today 5-y`
- geography: `US`
- top anchor: `Pikachu Pokemon`
- lower zero-retest anchor: `Pokemon Trainer`
- capture version: `collector_trends_anchor_v1`

The existing C3B research code percentile-ranks each window separately and currently combines the resulting Trainer-only percentile scores as:

`0.40 × Trainer 12m percentile + 0.60 × Trainer 5y percentile`

That formula is an existing research choice, not re-approved or changed by this source-authority study.

## 3. Live production-data coverage audit

Read-only audit of the current production Collector tables:

| Measure | Current value |
|---|---:|
| Active Trainer entities | 272 |
| Trainer entities linked to at least one card | 258 |
| Distinct linked Trainer cards across all card supertypes | 865 |
| Active Trainer subject links | 895 |
| Linked Trainer entities with any nonzero 5y signal | 219 / 258 = 84.9% |
| Linked Trainer entities with nonzero signal in both 12m and 5y | 182 / 258 = 70.5% |
| Linked Trainer entities with no nonzero signal in either window | 39 / 258 = 15.1% |
| Linked Trainer cards with any 5y-signal subject | 765 / 865 = 88.4% |
| Linked Trainer cards with no 5y-signal subject | 100 / 865 = 11.6% |
| Linked Trainer cards with any 12m-signal subject | 673 / 865 = 77.8% |
| Compound/multi-Trainer linked cards | 27 |

The 5-year capture itself passed the existing source-quality gate with:

- 272 / 272 entities retrieved
- 100% retrieval coverage
- 0% missing-or-failed share
- 83.8% observable nonzero signal coverage
- 44 confirmed below-threshold/zero observations
- anchor bridge integrity passed
- apparent zeros retested

The 12-month capture also passed:

- 272 / 272 entities retrieved
- 100% retrieval coverage
- 0% missing-or-failed share
- 69.9% observable nonzero signal coverage
- 82 confirmed below-threshold/zero observations
- anchor bridge integrity passed
- apparent zeros retested

The lower 12-month observable coverage is expected for a narrower window and does not indicate source failure.

## 4. Window stability

The two Trainer windows are not independent evidence families, but they are useful separate time horizons within the same source family.

Across the 258 Trainer identities currently linked to cards:

- Pearson correlation, raw normalized 12m vs 5y: **0.873**
- Spearman rank correlation, 12m vs 5y: **0.880**
- Current 40/60 blend vs 12m rank: **0.935**
- Current 40/60 blend vs 5y rank: **0.986**
- median absolute 12m-vs-5y percentile gap: **7.66 points**
- mean absolute percentile gap: **11.80 points**
- p90 absolute percentile gap: **29.49 points**
- zero/nonzero status differs between windows for 37 / 258 linked identities

Interpretation:

1. The windows broadly agree, so Trainer evidence is not unstable or contradictory.
2. The 5-year component provides the dominant long-run ordering under the current 60% weight.
3. The 12-month window still contributes useful recency information; newer/recent characters can move materially relative to their longer-run position.
4. Nothing in this source research justifies changing the 40/60 weighting. That belongs to scoring research, not source-authority research.

Examples of large 12m-vs-5y percentile differences include Irida, Professor Sada, Clavell, Jacq, Adaman, Ingo, Klara, Grusha, Miriam, and other recent-era characters. This is directionally consistent with the two windows measuring different time horizons rather than being redundant copies.

## 5. Identity mapping quality

Trainer identity mapping is strong where a canonical Trainer subject actually exists.

Current active subject-link methods:

| Mapping method | Links | Cards | Mean confidence | Minimum confidence |
|---|---:|---:|---:|---:|
| exact Trainer name | 557 | 557 | 1.000 | 1.00 |
| possessive Trainer name | 242 | 242 | 0.980 | 0.98 |
| explicit title subject | 41 | 40 | 0.999 | 0.98 |
| compound exact Trainer identity | 55 | 26 | 0.980 | 0.98 |

This is sufficient for an authority that scores named Trainer identities.

### Trainer-supertype cards are not all Trainer personalities

There are 2,653 eligible Trainer-supertype cards, but only 811 currently carry named-Trainer subject links. That raw 30.6% number is **not** an identity-coverage failure because most Trainer-supertype cards are Items, Tools, Stadiums, generic roles, or intentionally ambiguous Supporters.

Breakdown:

| Trainer card subtype | Cards | Named-Trainer linked |
|---|---:|---:|
| Supporter | 1,089 | 811 (74.5%) |
| Item | 816 | 0 |
| Tool | 294 | 0 |
| Stadium | 244 | 0 |
| Other | 210 | 0 |

The unlinked Supporter remainder is heavily populated by cards such as `Professor's Research`, `Boss's Orders`, `Copycat`, `Judge`, `Pokémon Center Lady`, `Pokémon Fan Club`, `TV Reporter`, `Fisherman`, `Gym Trainer`, `Lady`, generic grunts, occupation titles, and similar identities where guessing a unique fictional character would be incorrect.

Therefore the current conservative subject-identity policy should remain: **false split / unavailable is preferable to inventing a named Trainer identity.**

## 6. Google Trends query identity

Current query behavior is deliberately disambiguated:

- default Trainer query: `<Trainer Name> Pokemon`
- pre-registered collision-risk query: `<Trainer Name> Pokemon trainer`
- high-collision names are maintained in a versioned override registry
- examples include Aaron, Barry, Bianca, Blue, Brock, Dawn, Iris, Jessie, Karen, Larry, Leon, May, Misty, N, Red, Sabrina, Steven, Whitney, and others

Apparent zeros are retested against the lower `Pokemon Trainer` anchor before being accepted as below-threshold observations.

This is a reasonable free-source implementation and does not need to block Trainer Appeal.

### Semantic rule for zero observations

A confirmed Google Trends zero must **not** be described as "nobody likes this Trainer" or literal zero fan demand.

Google Trends is sampled and normalized search-interest data. Exact search terms can fall below observable volume. The current source should therefore interpret a confirmed zero as:

> **bottom-of-observable Trainer search interest for this source/window/query contract**

This is still a valid relative observation inside the Trainer-specific bucket.

Examples such as Brock, Sabrina, Steven, Iris, Bianca, Jessie, Larry, Whitney, and Lt. Surge currently fall into the confirmed-zero 5-year group despite being recognizable characters. That does not invalidate Google Trends as a relative Trainer signal; it defines the lower-resolution limit of the source.

## 7. Source semantics

Google Trends measures **search interest**, not direct stated preference.

That is acceptable for the current Trainer bucket as long as the public/internal definition remains honest. The Trainer signal should not be described as a literal fan-vote percentage or direct survey of collector willingness to own the card.

Recommended semantic definition:

> **Trainer Appeal is a relative, price-independent measure of audience interest in named Pokémon Trainer characters, currently derived from long-term and recent Google search-interest evidence.**

The word `relative` matters. The score is meaningful within the Trainer evidence universe; it does not need to assert that a Trainer score of 80 is the same raw type of evidence as a Pokémon score of 80 or an Artist score of 80.

That cross-bucket combination is a separate Collector Appeal aggregation problem.

## 8. External source research — non-blocking

Other evidence sources were investigated. None should block the current Trainer authority.

### Direct character-ranking / fan-poll sites

Some current public rankings can provide explicit character preference data, but coverage, methodology, licensing, commercial-use permission, stability, and scrapeability vary. They may be useful later as validation or a supplemental source.

They are **not required** for the current authority.

### Official Pokémon polls

Official Pokémon/Pokémon Masters/Nintendo publication polls are high-quality event evidence but are sparse, generation-specific, or ask context-specific questions. They are useful validation snapshots rather than a complete recurring authority.

### Wikimedia

Pageview data is free and useful as an independent attention diagnostic, but it measures information seeking rather than collector preference and has substantial page/identity coverage variability. It is optional validation, not required production input.

### Google Trends official API / Topics

Google recommends Topics rather than literal search terms when a suitable Topic exists because Topics consolidate related terms and language variants. The official Trends API remains an alpha-access opportunity and could improve scaling/reliability later.

Neither is necessary to proceed today. The existing source path already passed its operational quality gates.

## 9. Refresh cadence

Because Trainer Appeal is an audience-interest signal rather than a price feed, it does not need daily scraping.

Recommended cadence with the current free source:

- **12-month Trainer Trends:** weekly
- **5-year Trainer Trends:** monthly
- **query-override / identity registry:** change only through reviewed versioned edits
- **full source-quality gate:** every committed source run

Why:

- weekly 12m captures are enough to reflect meaningful recency shifts;
- 5y ordering should move slowly, so monthly is sufficient;
- this avoids unnecessary Google requests and VM/database load;
- raw source runs remain append-only/versioned, so history can accumulate for later stability studies.

A twice-weekly 12m cadence is also operationally acceptable if it fits the existing Collector refresh schedule, but the research does not show a need for more frequent collection.

## 10. Authority rules to carry forward

This research supports the following source-authority contract:

1. `google_trends_trainer` is the current authoritative Trainer evidence family.
2. 12m and 5y are two horizons from the same authority, not independent sources.
3. Named Trainer identities only; generic Trainer-card roles remain outside Trainer Appeal unless separately resolved.
4. Compound Trainer cards preserve their multiple canonical Trainer identities and contribution weights.
5. Confirmed Trends zero is a valid lower-bound source observation, not literal zero human preference.
6. Provider failures/rate limits/unresolved identity are **missing/unavailable**, not zero.
7. Price, card rarity, market value, card sales, pull rate, and Playability do not enter Trainer source scoring.
8. Playability remains a separate component/lift question.
9. Trainer evidence stays in its own bucket; no requirement exists for its raw source composition to match Pokémon or Artist evidence.
10. Future sources may enrich or validate Trainer Appeal but do not automatically replace or re-weight the current authority.

## 11. Final disposition

### Supported now

- Trainer identity domain: **SUPPORTED**
- Trainer card/entity mapping: **SUPPORTED**
- Google Trends 12m source quality: **SUPPORTED**
- Google Trends 5y source quality: **SUPPORTED**
- multi-window Trainer evidence stability: **SUPPORTED**
- Trainer-specific source authority: **SUPPORTED WITH LIMITATIONS**
- price independence: **SUPPORTED**
- weekly/monthly recurring refresh: **SUPPORTED**

### Not decided here

- final Trainer Appeal formula
- final 12m/5y weighting
- treatment of lower-bound zero observations in final scoring
- any Trainer-to-Pokémon bucket weight or aggregation rule
- any Collector Appeal V6/V7 scoring modification

### Decision token

`TRAINER_APPEAL_SOURCE_AUTHORITY_SUPPORTED_WITH_LIMITATIONS`

The project should move on from Trainer **source discovery**. The next Trainer-related work should use the existing Google Trends authority and address scoring/aggregation separately rather than continuing to search indefinitely for a Pokémon-identical source stack.

## 12. Primary references

Internal implementation:

- `backend/scripts/ingest_collector_google_trends.py`
- `backend/config/pokemon_collector_trainer_query_overrides_v1.json`
- `backend/scripts/research_collector_c3b_playability_lift.py`
- `pokemon_collector_entity_reference`
- `pokemon_card_collector_entity_links`
- `pokemon_collector_entity_observations`
- `pokemon_collector_source_runs`

External source semantics:

- Google Trends FAQ: https://support.google.com/trends/answer/4365533
- Google Trends terms vs topics: https://support.google.com/trends/answer/17309543
- Google Trends export/use guidance: https://support.google.com/trends/answer/4365538

No production write or scoring change was performed for this research.
