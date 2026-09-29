# Collector Cross-Domain Calibration V1 — Final Historical Replay

## A. Historical authority correction

Original V7 used `pokemon_canonical_card_market_prices_latest`. The rejected `get_pokemon_cards_daily_constituents` reader is a later Set Value abstraction. The corrected replay uses `get_pokemon_market_root_standard_card_prices_as_of_v2` for each frozen root Set at 2026-09-11. Neither production RPC changed.

## B. Price coverage

Frozen membership: 4331; historically priced: 4331; coverage: 100.00%. All six reviewed Prismatic ACE SPEC cards were recovered. The 24 structural exclusions remain `no_modeled_pull_probability`.

## C. Control replay

Per-Set max/mean rho error: 0.0 / 0.0. Sets within 1e-9: 22/22. Median rho: 0.31764708442997636; weighted rho: 0.29910491268326117; positive Sets: 95.45454545454545%. Gate: **PASS**. Spearman uses existing tie-aware average midranks.

## D. Candidate validation

| Candidate | Trainer Spearman | Weighted rho delta | Pair concordance delta | OOS R² delta | Held-out Spearman delta | All gates? |
|---|---:|---:|---:|---:|---:|:---:|
| ANCHOR25 | 0.999866 | +0.001986 | +0.003898 | +0.000898 | +0.000711 | YES |
| ANCHOR50 | 0.999303 | +0.004097 | +0.012474 | +0.001654 | +0.001276 | YES |
| ANCHOR75 | 0.997883 | +0.006707 | +0.031185 | +0.002211 | +0.001666 | YES |
| ANCHOR100 | 0.992562 | +0.010792 | +0.047817 | +0.002520 | +0.001849 | NO |

Pokémon, Artist, Playability, and neutral behavior remain unchanged. Negative controls remain documentation-only.

## E. Bootstrap

1,000 deterministic whole-Set draws, seed 20260929.

| Candidate | Weighted rho CI | Median rho CI | Pair concordance CI | OOS R² CI | Held-out Spearman CI |
|---|---|---|---|---|---|
| ANCHOR25 | [0.0009311417048605789, 0.003173700341785883] | [-0.0004270759815110381, 0.007302054599693908] | [-0.006281862973536506, 0.01421122976941506] | [0.0005683057512458455, 0.001257959050521723] | [0.00014519379023058277, 0.0012699820224876448] |
| ANCHOR50 | [0.0022862744856574453, 0.006070878962673265] | [-0.0006669802642050859, 0.013915449262924373] | [-0.005278148652294551, 0.029088088986257723] | [0.001017905415491141, 0.0023477752137693233] | [0.0002308232734208632, 0.0023286797386778218] |
| ANCHOR75 | [0.0034909526915220188, 0.009963737598879432] | [-0.002245480906858943, 0.022418684104165365] | [0.0080425878629894, 0.05424947176341488] | [0.0012767603360463232, 0.003196610642033212] | [0.0001962981787982071, 0.003091155363341049] |
| ANCHOR100 | [0.005397159151377294, 0.016417135719079937] | [-0.006804273609271383, 0.030116453050194614] | [0.013935831476203373, 0.08015772773252619] | [0.001339667118598012, 0.003743509282432883] | [2.825465874017908e-06, 0.0036150404479092847] |

## F. Set-level shadow

`{"CONTROL":{"rankCorrelation":1.0,"maxRankMove":0},"ANCHOR25":{"rankCorrelation":1.0,"maxRankMove":0},"ANCHOR50":{"rankCorrelation":1.0,"maxRankMove":0},"ANCHOR75":{"rankCorrelation":0.9988706945228685,"maxRankMove":1},"ANCHOR100":{"rankCorrelation":0.9988706945228685,"maxRankMove":1}}`. Nothing was published and Overall RIP was unchanged.

## G. Named cases

Gengar, Giovanni, Cynthia, Lillie, and high/mid/low examples remain diagnostic only.

## H. Decision

**ANCHOR25_SHADOW_SUPPORTED** — Smallest preregistered candidate passing every gate. Shadow support is not Collector V8 promotion.

## I. Production safety

Production mutations: **NONE**

## J. Git

Branch: `research/collector-cross-domain-calibration-v1-20260929`. Old SHA: `3624102d0b1ae61fc13e161963ea4678cf3ff7fe`. New SHA is in the final handoff. Pushed: YES after commit. Merge: NO. Main: untouched. Deployment: NO.

COLLECTOR_CROSS_DOMAIN_CALIBRATION_V1_FINAL_READY_FOR_REVIEW
