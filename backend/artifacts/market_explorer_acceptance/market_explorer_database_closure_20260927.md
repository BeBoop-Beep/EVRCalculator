# Market Explorer Database Closure — 2026-09-27

## Final authority

- Serving generation: `96740b15-88d7-455d-bf64-c9da57cf26ab`
- Comparison watermark: `2026-09-27`
- Classification: `sealed-product-classification-v5-consumer-retail-taxonomy`
- Consumer policy: `market-explorer-consumer-sealed-v3-nonbulk-retail`
- Serving freshness health: CURRENT, lag 0 days, maintained cache 37/37 current.
- Set-page ↔ Explorer parity: PASS — 134/134 sets, 1,378/1,378 product identities, 0 missing, 0 extra, 0 tracked-value/count mismatches.

## Consumer parent membership — same-date 30-day-fresh comparison

Old narrow overview-family policy: **432** current products. Corrected consumer-retail non-bulk policy: **1378** current products.

| Family | Inventory | Fresh priced | Old parent | New parent |
|---|---:|---:|---:|---:|
| battle_deck | 6 | 6 | 0 | 6 |
| binder | 8 | 7 | 0 | 7 |
| booster_box | 55 | 51 | 51 | 51 |
| booster_bundle | 36 | 29 | 29 | 29 |
| booster_pack_art_bundle | 48 | 48 | 0 | 48 |
| build_and_battle_box | 31 | 31 | 0 | 31 |
| build_and_battle_stadium | 10 | 10 | 0 | 10 |
| case | 193 | 182 | 0 | 0 |
| chest | 5 | 5 | 0 | 5 |
| collection_box | 12 | 12 | 0 | 12 |
| collection_product | 138 | 126 | 0 | 126 |
| display | 50 | 44 | 0 | 0 |
| elite_trainer_box | 83 | 79 | 79 | 79 |
| enhanced_booster_box | 2 | 2 | 2 | 2 |
| first_partner_pack | 8 | 0 | 0 | 0 |
| fun_pack | 14 | 13 | 0 | 13 |
| half_booster_box | 9 | 9 | 9 | 9 |
| loose_booster_pack | 139 | 129 | 129 | 129 |
| master_carton | 1 | 1 | 0 | 0 |
| mini_tin | 85 | 85 | 0 | 85 |
| multi_product_bundle | 18 | 18 | 0 | 18 |
| other | 110 | 82 | 0 | 82 |
| other_blister | 8 | 8 | 0 | 8 |
| pokemon_center_elite_trainer_box | 42 | 42 | 42 | 42 |
| poster | 6 | 6 | 0 | 6 |
| premium_collection | 42 | 41 | 0 | 41 |
| prerelease_product | 11 | 11 | 0 | 11 |
| single_pack_blister | 170 | 161 | 0 | 161 |
| sleeved_booster_pack | 95 | 91 | 91 | 91 |
| super_premium_collection | 4 | 4 | 0 | 4 |
| theme_deck | 98 | 78 | 0 | 78 |
| three_pack_blister | 86 | 80 | 0 | 80 |
| tin | 112 | 101 | 0 | 101 |
| two_pack_blister | 6 | 6 | 0 | 6 |
| ultra_premium_collection | 7 | 7 | 0 | 7 |
| world_championship_deck | 25 | 0 | 0 | 0 |

## Surface counts — before → final

| Sealed scope | Before (Sep-26 generation) | Final Sep-27 |
|---|---:|---:|
| Parent | 1 | 1 |
| Set | 130 | 134 |
| Era | 15 | 16 |
| Quick | 6 | 6 |
| Type | 17 | 35 (34 current canonical types + Packs composite) |

## Canonical Sealed Type audit

| Key | Label | Products | Current priced | Sets | Eras | First | Latest | Bulk | Consumer parent | Prepared key | State |
|---|---|---:|---:|---:|---:|---|---|---|---|---|---|
| battle_deck | Battle Deck | 6 | 6 | 3 | 2 | 2026-07-01 | 2026-09-27 | false | true | sealed-type:battle_deck | PREPARED_CANDIDATE |
| binder | Binder | 8 | 7 | 6 | 3 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:binder | PREPARED_CANDIDATE |
| booster_box | Booster Box | 55 | 51 | 55 | 10 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:booster_box | PREPARED_CANDIDATE |
| booster_bundle | Booster Bundle | 36 | 29 | 29 | 4 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:booster_bundle | PREPARED_CANDIDATE |
| booster_pack_art_bundle | Booster Pack Art Bundle | 48 | 48 | 48 | 5 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:booster_pack_art_bundle | PREPARED_CANDIDATE |
| build_and_battle_box | Build & Battle Box | 31 | 31 | 30 | 4 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:build_and_battle_box | PREPARED_CANDIDATE |
| build_and_battle_stadium | Build & Battle Stadium | 10 | 10 | 10 | 2 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:build_and_battle_stadium | PREPARED_CANDIDATE |
| case | Case | 193 | 182 | 47 | 6 | 2026-04-07 | 2026-09-27 | true | false | sealed-type:case | PREPARED_CANDIDATE |
| chest | Chest | 5 | 5 | 5 | 2 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:chest | PREPARED_CANDIDATE |
| collection_box | Collection Box | 12 | 12 | 2 | 1 | 2026-06-28 | 2026-09-27 | false | true | sealed-type:collection_box | PREPARED_CANDIDATE |
| collection_product | Collection Product | 138 | 126 | 36 | 6 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:collection_product | PREPARED_CANDIDATE |
| display | Display | 50 | 44 | 39 | 4 | 2026-04-07 | 2026-09-27 | true | false | sealed-type:display | PREPARED_CANDIDATE |
| elite_trainer_box | Elite Trainer Box | 83 | 79 | 63 | 5 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:elite_trainer_box | PREPARED_CANDIDATE |
| enhanced_booster_box | Enhanced Booster Box | 2 | 2 | 2 | 2 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:enhanced_booster_box | PREPARED_CANDIDATE |
| first_partner_pack | First Partner Pack | 8 | 0 | 1 | 1 | 2026-08-02 | 2026-08-02 | false | true | — | UNAVAILABLE |
| fun_pack | Fun Pack | 14 | 13 | 13 | 3 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:fun_pack | PREPARED_CANDIDATE |
| half_booster_box | Half Booster Box | 9 | 9 | 9 | 3 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:half_booster_box | PREPARED_CANDIDATE |
| loose_booster_pack | Loose Booster Pack | 139 | 129 | 127 | 15 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:loose_booster_pack | PREPARED_CANDIDATE |
| master_carton | Master Carton | 1 | 1 | 1 | 1 | 2026-06-27 | 2026-09-27 | true | false | sealed-type:master_carton | PREPARED_CANDIDATE |
| mini_tin | Mini Tin | 85 | 85 | 12 | 3 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:mini_tin | PREPARED_CANDIDATE |
| multi_product_bundle | Multi-Product Bundle | 18 | 18 | 13 | 4 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:multi_product_bundle | PREPARED_CANDIDATE |
| other | Other | 110 | 82 | 57 | 10 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:other | PREPARED_CANDIDATE |
| other_blister | Other Blister | 8 | 8 | 4 | 3 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:other_blister | PREPARED_CANDIDATE |
| pokemon_center_elite_trainer_box | Pokémon Center Elite Trainer Box | 42 | 42 | 34 | 3 | 2026-04-07 | 2026-09-27 | false | true | sealed-type:pokemon_center_elite_trainer_box | PREPARED_CANDIDATE |
| poster | Poster Collection | 6 | 6 | 5 | 2 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:poster | PREPARED_CANDIDATE |
| premium_collection | Premium Collection | 42 | 41 | 21 | 5 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:premium_collection | PREPARED_CANDIDATE |
| prerelease_product | Prerelease Product | 11 | 11 | 11 | 2 | 2026-06-28 | 2026-09-27 | false | true | sealed-type:prerelease_product | PREPARED_CANDIDATE |
| single_pack_blister | Single-Pack Blister | 170 | 161 | 43 | 5 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:single_pack_blister | PREPARED_CANDIDATE |
| sleeved_booster_pack | Sleeved Booster Pack | 95 | 91 | 46 | 5 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:sleeved_booster_pack | PREPARED_CANDIDATE |
| super_premium_collection | Super-Premium Collection | 4 | 4 | 4 | 3 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:super_premium_collection | PREPARED_CANDIDATE |
| theme_deck | Theme Deck | 98 | 78 | 51 | 12 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:theme_deck | PREPARED_CANDIDATE |
| three_pack_blister | Three-Pack Blister | 86 | 80 | 45 | 6 | 2026-04-11 | 2026-09-27 | false | true | sealed-type:three_pack_blister | PREPARED_CANDIDATE |
| tin | Tin | 112 | 101 | 30 | 6 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:tin | PREPARED_CANDIDATE |
| two_pack_blister | Two-Pack Blister | 6 | 6 | 6 | 5 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:two_pack_blister | PREPARED_CANDIDATE |
| ultra_premium_collection | Ultra-Premium Collection | 7 | 7 | 5 | 4 | 2026-06-27 | 2026-09-27 | false | true | sealed-type:ultra_premium_collection | PREPARED_CANDIDATE |
| world_championship_deck | World Championship Deck | 25 | 0 | 1 | 1 | 2026-08-02 | 2026-08-02 | false | true | — | UNAVAILABLE |

Every canonical family with current pricing has a V2 Type market. `first_partner_pack` and `world_championship_deck` remain visible but unavailable because their latest pricing is 2026-08-02, outside the 30-day current-pricing window. Cases, displays, and master cartons remain valid Type markets but are excluded from consumer parents.

## Residual `other` population

- Inventory products: 110
- Current priced products: 82
- These remain residual because the current deterministic taxonomy cannot truthfully assign a narrower repeatable class.

Examples:

- 30th Celebration Greninja ex Box — ME: 30th Celebration — latest 2026-09-27 — $67.0
- 30th Celebration Pack — ME: 30th Celebration — latest 2026-08-02 — $27.63
- 30th Celebration Sylveon ex Box — ME: 30th Celebration — latest 2026-09-27 — $67.2
- Alakazam V Box — Vivid Voltage — latest 2026-09-27 — $60.71
- Alolan Marowak GX Box — Unbroken Bonds — latest 2026-04-28 — $587.0
- Alolan Ninetales GX Challenge Box — Burning Shadows — latest 2026-09-27 — $97.5
- Ascended Heroes Mega Emboar ex Box — Ascended Heroes — latest 2026-09-27 — $57.22
- Ascended Heroes Mega Feraligatr ex Box — Ascended Heroes — latest 2026-09-27 — $58.23
- Ascended Heroes Mega Meganium ex Box — Ascended Heroes — latest 2026-09-27 — $55.61
- Ash-Greninja EX Box — Fates Collide — latest 2026-06-20 — $349.99
- Astral Radiance 3 Pack Hanger Box — Astral Radiance — latest 2026-09-27 — $42.5
- Aurorus EX Box — BREAKthrough — latest 2026-09-27 — $399.0
- Base Set 2 - 2-Player CD-ROM Starter Set — Base Set 2 — latest 2026-09-27 — $170.76
- Battle Arena Deck [Mega Blastoise] — Celestial Storm — latest 2026-09-27 — $295.99
- Battle Arena Decks: Black Kyurem EX vs White Kyurem EX — Guardians Rising — latest 2026-09-27 — $54.65
- Battle Arena Decks: Keldeo EX vs Rayquaza EX — Steam Siege — latest 2026-09-27 — $167.93
- Battle Arena Decks: Mewtwo EX vs Darkrai EX — Ancient Origins — latest 2026-05-30 — $299.99
- Battle Arena Decks: Xerneas vs Yveltal — Furious Fists — latest 2026-09-27 — $90.0
- Bewear GX Box — Guardians Rising — latest 2026-09-27 — $277.97
- Black and White Preview Pack — Black & White — latest 2026-09-27 — $36.0

## Screens, Graded, movement, and publication proofs

- Global Screen request with `p_limit=25` returned exactly 10 rows, mixed `cards` + `sealed`, all at 2026-09-27.
- Graded authority remains insufficient: 1 graded variant, 1 observation, 0 published Graded markets; asset options return `INSUFFICIENT_AUTHORITY`.
- Sealed movement RPC accepts 1–100 IDs and returns independent 1D/7D/30D/3M movement. On a 100-product serving sample: 50 distinct 7D movements; missing 30D=4 and missing 3M=11; all missing baselines remained NULL.
- Live `EXPLAIN (ANALYZE, BUFFERS)` on the 100-product lookup: 109.669 ms total execution, 49,708 shared-hit blocks, 0 shared-read blocks, 100 rows returned.
- Raw composition: 156 frozen Set Value roots, 19,728 leaves, basket value $433,816.83; exact reconciliation passed.
- Canonical validation: VALIDATED with zero issues; coherence assertion: COHERENT.
- Bulk leak audit over Total/Set/Era/Quick consumer markets: 0.
- Freshness root cause: current-day sources were ready, but the V2 publisher was blocked first by stale rarity certification and incomplete frozen Set Value rosters; the monolithic connector invocation also exceeded its session envelope. Rarity certification was advanced fail-closed, all 156 rosters were reconciled, and the final generation was built in bounded canonical stages and promoted atomically.
