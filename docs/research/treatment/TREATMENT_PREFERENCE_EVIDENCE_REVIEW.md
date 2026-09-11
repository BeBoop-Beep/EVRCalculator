# Treatment Preference T2 — Price-Independent Evidence Review

Status: `TREATMENT_PREFERENCE_INSUFFICIENT_EVIDENCE`  
Collector impact: `TREATMENT_SHOULD_REMAIN_DIAGNOSTIC`  
Study date: 2026-09-11

## Executive finding

Treatment Preference is plausible, but the evidence available today does not support an authority without first-party voting. The review found two sources with a direct preference format, six indirect qualitative sources, three design/taxonomy references, four market-contaminated sources, and one unusable source. None supplies a reproducible, adequately sampled, price-blind treatment contrast that separates subject, artist, and scarcity.

Consequently, T2 freezes no score and no pairwise order. Treatment remains a diagnostic descriptor. Market validation and the Appeal × Treatment interaction were not eligible and were not run.

## Identification boundary

Preference construction excludes prices, sales, pull rates, rarity ranks, grading populations, listing scarcity, set values, and premiums. These can validate a previously frozen preference authority, but cannot define one.

T1 provides strong places to test a future outcome—2 same-card, 6,251 same-subject, 87 scarcity-matched, and 6,253 era-local contrasts. Those cohorts are controls, not collector responses. Their frozen fingerprints remain unchanged in `treatment_preference_candidate_manifest.json`.

## Source audit

The most promising design is Tokyo Legends' [Art Vote](https://tltcg.com/art), which presents two cards and asks for the better illustration. At review time it published no completed comparisons, so it contributes zero observations and no recoverable treatment edge.

The official Pokémon community [favorite Illustration Rare poll](https://community.pokemon.com/en-us/discussion/14244/favorite-illustration-rare-charizard) is a direct vote but has only two votes and changes the card, subject, and artist. It tests favorite cards, not treatment.

Modern qualitative evidence includes Reddit discussions of [rainbow versus gold](https://www.reddit.com/r/PokemonTCG/comments/14oqw4v/rainbow_vs_gold_secret_rares_which_do_you_prefer/), [Illustration Rares generally](https://www.reddit.com/r/PokemonTCG/comments/1jdyw4o/ill_die_on_this_hill_illustration_rares_are_the/), and [favorite Illustration Rare art](https://www.reddit.com/r/PokemonTCG/comments/1ed10k8/which_illustration_rare_cards_art_goes_the_hardest/). They demonstrate vocabulary and enthusiasm, but their self-selected comments/upvotes do not isolate presentation; the rainbow/gold poll result is not recoverable.

The strongest historical source is a 2012 PokéBeach [favorite card-art discussion](https://www.pokebeach.com/forums/threads/favorite-pokemon-card-art.109444/). Its comments explicitly expose ownership, rarity, and value confounding, and comparisons change subject and artist.

Official Pokémon references establish treatment meaning, not preference: the [Scarlet & Violet rarity/aesthetic revision](https://www.pokemon.com/uk/pokemon-news/pokemon-tcg-scarlet-violet-revamps-pokemon-tcg-card-aesthetic), the [Radiant Pokémon rulebook](https://assets.pokemon.com/assets/cms2/pdf/trading-card-game/rulebook/swsh10_rulebook_en.pdf), and the [HGSS checklist](https://assets.pokemon.com/assets/cms/pdf/tcg/checklists/HGSS4_Cardlist_Lo.pdf).

Market-based claims were rejected from construction. Examples include TCGplayer's [rarity-change analysis](https://www.tcgplayer.com/content/article/robot/d3d9fbf9-5501-4c34-bdfd-4e47c9900312), a [best-SIR collectability ranking](https://pokemasterstcg.com/article/142-best-special-illustration-rares-to-collect), a [transaction-data study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0334289), and [foil-tier price histories](https://www.moonstonehq.com/articles/art-floor-foil-tiers). These may be relevant after preregistration, never before it.

The complete field-level audit—including sample, population, visible price/rarity, labels, era, subject/artist changes, response granularity, reproducibility, reuse, and bias—is in `treatment_preference_sources.json`.

## Era-local results

| Era | Candidate comparisons | Result | Why |
|---|---|---|---|
| Scarlet & Violet | SIR/IR, illustration-led/full-art, gold, shiny | `INSUFFICIENT_EVIDENCE` | Discussion exists, but no usable controlled outcome. |
| Sword & Shield | alternate art, gallery, rainbow/gold, Radiant | `INSUFFICIENT_EVIDENCE` | The only treatment-specific poll result is unrecoverable and uncontrolled. |
| Sun & Moon | rainbow, gold, alternate/full-art | `INSUFFICIENT_EVIDENCE` | No direct price-blind treatment contrast located. |
| XY | full-art, secret rare, special foil | `INSUFFICIENT_EVIDENCE` | No direct price-blind treatment contrast located. |
| Vintage | holo/non-holo and specialty presentation | `INSUFFICIENT_EVIDENCE` | Anecdotes are value, rarity, ownership, subject, and artist confounded. |

No cross-era inference is permitted. Identically named features can carry different meanings and visual implementations across eras.

## Semantic attributes

No attribute is supported as a preference authority. `illustration_led`, `full_art`, `alternate_artwork`, `textured`, `gold_or_gilded`, `rainbow`, `shiny`, `gallery_style`, `premium_frame`, `character_scene`, `special_foil`, and `vintage_specialty` all remain `INSUFFICIENT`. Some have low qualitative plausibility, but plausibility is not an estimand.

## Graph and confidence

The graph records three indirect-only candidate relationships and zero accepted direct edges. All nine represented nodes are disconnected for authority purposes. Cardinal and ordinal scoring therefore fail the connectivity gate; no unsupported order is inferred through transitivity.

The confidence vocabulary is `HIGH`, `MEDIUM`, `LOW`, and `INSUFFICIENT`. Confidence depends on direct sample size, source independence, structural matching, era consistency, and ambiguity. Price agreement is excluded. Every era and attribute is `INSUFFICIENT` in T2.

## Decision and next evidence needed

Authority type is `D_NO_SCORE`. A future study should collect blinded pairwise choices within era, randomize side/order, avoid prices and rarity cues where visually separable, oversample T1 same-card and scarcity-matched pairs, record individual responses, and preregister aggregation before any market validation.

No Collector V7, taxonomy V3, Overall RIP, database, production score, or market-validation artifact was modified or created by this study.
