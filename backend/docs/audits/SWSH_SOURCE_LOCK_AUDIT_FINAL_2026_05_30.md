### 1. Summary
- number of sets audited: 12
- number of buckets audited: 148
- number of mismatches found: 1
- number of source URL issues found: 4
- number of buckets fixed: 30
- number of buckets downgraded: 0
- number of sets needing re-simulation: 1 (swsh5)

### 2. Source hierarchy findings
- swsh1 (Sword & Shield):
  - TCGplayer pull-rate study found: no
  - primary source selected: None
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh10 (Astral Radiance):
  - TCGplayer pull-rate study found: yes
  - primary source selected: astral_radiance_tcgplayer_empirical
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Astral-Radiance-Pull-Rates/10da749f-9c8b-45c0-b80a-dbd86ca5dcde/
- swsh11 (Lost Origin):
  - TCGplayer pull-rate study found: yes
  - primary source selected: None
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Lost-Origin-Pull-Rates/ba20ac4d-9448-45ce-b919-d856d107c744/
- swsh12 (Silver Tempest):
  - TCGplayer pull-rate study found: yes
  - primary source selected: silver_tempest_tcgplayer_empirical
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Silver-Tempest-Pull-Rates/6490d591-e582-4930-8446-00e190876d30/
- swsh2 (Rebel Clash):
  - TCGplayer pull-rate study found: no
  - primary source selected: None
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh3 (Darkness Ablaze):
  - TCGplayer pull-rate study found: no
  - primary source selected: None
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh4 (Vivid Voltage):
  - TCGplayer pull-rate study found: no
  - primary source selected: swsh4_digitaltq_primary_630_2023_11_07
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh5 (Battle Styles):
  - TCGplayer pull-rate study found: no
  - primary source selected: battle_styles_community_pack_study
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh6 (Chilling Reign):
  - TCGplayer pull-rate study found: no
  - primary source selected: charizardx_user_rows
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh7 (Evolving Skies):
  - TCGplayer pull-rate study found: yes
  - primary source selected: tcgplayer_evolving_skies_8000_pack
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Evolving-Skies-Pull-Rates/6a743d7b-e5ee-4fd6-9d18-64a636990e8c/
- swsh8 (Fusion Strike):
  - TCGplayer pull-rate study found: no
  - primary source selected: fusion_strike_tcgplayer_instagram_4000plus_2021_11
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A
- swsh9 (Brilliant Stars):
  - TCGplayer pull-rate study found: no
  - primary source selected: brilliant_stars_reddit_2160_pack_study_2022_03
  - secondary sources used: ThePriceDex cross-reference and/or supplementary community discussion where present
  - ThePriceDex role: secondary_index only
  - source confidence: config-defined (high/medium_high/medium by set)
  - TCGplayer exact URL: N/A

### 3. Battle Styles findings
- exact source selected for Battle Styles: https://www.reddit.com/r/PokemonTCG/comments/mx0gvz/battle_styles_pull_data_after_almost_20000_packs/
- whether TCGplayer Battle Styles pull-rate study exists: no dedicated article confirmed in this audit
- exact Reddit/community source URL if used: https://www.reddit.com/r/PokemonTCG/comments/mx0gvz/battle_styles_pull_data_after_almost_20000_packs/
- ThePriceDex comparison: retained as SECONDARY_INDEX_ONLY, not direct
- alternate art v old value: 1/170
- alternate art v corrected value: 1/157
- where 1/170 came from: hardcoded in SetBattleStylesConfig.RARE_SLOT_PROBABILITY and BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE
- alternate art vmax value: 1/684 (confirmed and retained)
- regular V mapping: retained runtime bucket regular v; direct-source status unchanged
- regular VMAX mapping: retained runtime bucket regular vmax; ThePriceDex Rare Holo VMAX remains secondary index metadata only
- secret rare mapping: ThePriceDex Secret Rare remains broad secondary index label, not mapped as direct support for alternate art vmax
- files changed: backend/constants/tcg/pokemon/swordAndShieldEra/battleStyles.py, backend/tests/unit/db/services/test_explore_page_service.py
- tests added: source-lock helper tests and explicit negative anti-regression assertions for 1/170/1/454

### 4. Chilling Reign findings
- confirmation alternate art vmax uses 1/396: yes
- where old bad value came from, if known: historical stale direct-odds row in prior Chilling Reign mapping/audit constants (legacy alias rows)
- all direct rows audited: yes via runtime references and source-lock guardrail tests
- tests added: explicit negative assertion that 1/454 does not reappear

### 5. Set-by-set audit table
|set ID|bucket|source ID|source label|source odds|runtime odds|displayed odds|status before|status after|action taken|
|---|---|---|---|---|---|---|---|---|---|
|swsh1|amazing rare||Amazing Rare||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh1|full art|swsh1_elite_fourum_primary_4628_2020_02_13|Ultra Rare|1/26.75|1/26.7500|1/26.75|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh1|gold rare|swsh1_elite_fourum_primary_4628_2020_02_13|Secret Rare|1/110.19|1/110.1900|1/110.19|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh1|holo rare||Holo Rare residual|derived assumption|1/3|derived assumption|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh1|radiant or vstar||Radiant / VSTAR||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh1|rainbow rare|swsh1_elite_fourum_primary_4628_2020_02_13|Rainbow Rare|1/81.19|1/81.1900|1/81.19|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh1|rare||Rare residual|residual|1/2.2532|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh1|regular v|swsh1_elite_fourum_primary_4628_2020_02_13|Rare Holo V|1/7.04|1/7.0400|1/7.04|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh1|regular vmax|swsh1_elite_fourum_primary_4628_2020_02_13|Rare Holo VMAX|1/45.37|1/45.3700|1/45.37|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh1|thepricedex modeled row|swsh1_thepricedex_cross_reference_2026_05|ThePriceDex modeled/equal-distribution row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh1|trainer gallery||Trainer Gallery||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh10|alternate art v|astral_radiance_tcgplayer_empirical|Alternate Art V|1/190|1/190|1/190|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|full art|astral_radiance_tcgplayer_empirical|Full Art|1/65|1/65|1/65|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|gold rare|astral_radiance_tcgplayer_empirical|Gold Rare|1/120|1/120|1/120|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|radiant rare||Radiant Rare||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh10|rainbow rare|astral_radiance_tcgplayer_empirical|Rainbow Rare|1/110|1/110|1/110|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|rare||Rare residual|residual|1/2.4904|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh10|regular v|astral_radiance_tcgplayer_empirical|V|1/7.4|1/7.4000|1/7.4|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|regular vmax|astral_radiance_tcgplayer_empirical|VMAX|1/34|1/34|1/34|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|regular vstar|astral_radiance_tcgplayer_empirical|VSTAR|1/16|1/16|1/16|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh10|thepricedex inferred|astral_radiance_thepricedex_cross_reference_2026_05|ThePriceDex inferred row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh10|trainer gallery||Trainer Gallery (combined)||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh11|alternate art child split||Alternate art child split||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh11|alternate art v|lost_origin_tcgplayer_empirical|Alternate Art V|1/200|1/200|1/200|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|full art|lost_origin_tcgplayer_empirical|Full Art|1/70|1/70|1/70|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|gold rare|lost_origin_tcgplayer_empirical|Gold Rare|1/125|1/125|1/125|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|radiant rare||Radiant Rare||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh11|rainbow rare|lost_origin_tcgplayer_empirical|Rainbow Rare|1/115|1/115|1/115|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|rare||Rare residual|residual|1/2.4558|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh11|regular v|lost_origin_tcgplayer_empirical|V|1/7.6|1/7.6000|1/7.6|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|regular vmax|lost_origin_tcgplayer_empirical|VMAX|1/34|1/34|1/34|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|regular vstar|lost_origin_tcgplayer_empirical|VSTAR|1/16|1/16|1/16|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh11|thepricedex inferred|lost_origin_thepricedex_cross_reference_2026_05|ThePriceDex inferred row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh11|trainer gallery||Trainer Gallery (combined)||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh12|alternate art v|silver_tempest_tcgplayer_empirical|Alternate Art V|1/210|1/210|1/210|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|full art|silver_tempest_tcgplayer_empirical|Full Art|1/72|1/72|1/72|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|gold rare|silver_tempest_tcgplayer_empirical|Gold Rare|1/130|1/130|1/130|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|radiant rare||Radiant Rare||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh12|rainbow rare|silver_tempest_tcgplayer_empirical|Rainbow Rare|1/118|1/118|1/118|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|rare||Rare residual|residual|1/2.4238|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh12|regular v|silver_tempest_tcgplayer_empirical|V|1/7.8|1/7.8000|1/7.8|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|regular vmax|silver_tempest_tcgplayer_empirical|VMAX|1/35|1/35|1/35|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|regular vstar|silver_tempest_tcgplayer_empirical|VSTAR|1/16|1/16|1/16|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL|
|swsh12|thepricedex inferred|silver_tempest_thepricedex_cross_reference_2026_05|ThePriceDex inferred row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh12|trainer gallery||Trainer Gallery (combined)||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh2|amazing rare||Amazing Rare||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh2|full art|swsh2_elite_fourum_primary_2736_2020_07_18|Ultra Rare|1/26.56|1/26.5600|1/26.56|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh2|gold rare|swsh2_elite_fourum_primary_2736_2020_07_18|Secret Rare|1/105.23|1/105.2300|1/105.23|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh2|holo rare||Holo Rare residual|derived assumption|1/3|derived assumption|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh2|radiant or vstar||Radiant / VSTAR||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh2|rainbow rare|swsh2_elite_fourum_primary_2736_2020_07_18|Rainbow Rare|1/66.73|1/66.7300|1/66.73|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh2|rare||Rare residual|residual|1/2.2517|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh2|regular v|swsh2_elite_fourum_primary_2736_2020_07_18|Rare Holo V|1/7.91|1/7.9100|1/7.91|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh2|regular vmax|swsh2_elite_fourum_primary_2736_2020_07_18|Rare Holo VMAX|1/29.42|1/29.4200|1/29.42|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh2|thepricedex modeled row|swsh2_thepricedex_cross_reference_2026_05|ThePriceDex modeled/equal-distribution row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh2|trainer gallery||Trainer Gallery||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh3|amazing rare||Amazing Rare||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh3|full art|swsh3_elite_fourum_primary_5040_2020_09_16|Ultra Rare|1/25.98|1/25.9800|1/25.98|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh3|gold rare|swsh3_elite_fourum_primary_5040_2020_09_16|Secret Rare|1/114.55|1/114.5500|1/114.55|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh3|holo rare||Holo Rare residual|derived assumption|1/3|derived assumption|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh3|radiant or vstar||Radiant / VSTAR||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh3|rainbow rare|swsh3_elite_fourum_primary_5040_2020_09_16|Rainbow Rare|1/84.00|1/84|1/84.00|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh3|rare||Rare residual|residual|1/2.2560|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh3|regular v|swsh3_elite_fourum_primary_5040_2020_09_16|Rare Holo V|1/7.95|1/7.9500|1/7.95|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh3|regular vmax|swsh3_elite_fourum_primary_5040_2020_09_16|Rare Holo VMAX|1/25.98|1/25.9800|1/25.98|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh3|thepricedex modeled row|swsh3_thepricedex_cross_reference_2026_05|ThePriceDex modeled/equal-distribution row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh3|trainer gallery||Trainer Gallery||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh4|amazing rare|swsh4_digitaltq_primary_630_2023_11_07|Amazing Rare|1/17.5||1/17.5|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|full art|swsh4_digitaltq_primary_630_2023_11_07|Ultra Rare|1/25.2|1/25.1889|1/25.2|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|gold rare|swsh4_digitaltq_primary_630_2023_11_07|Secret Rare Holo|1/90.1|1/90.0901|1/90.1|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|holo rare|swsh4_digitaltq_primary_630_2023_11_07|Rare Holo|1/4.6|1/4.5977|1/4.6|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|radiant or vstar||Radiant / VSTAR||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh4|rainbow rare|swsh4_digitaltq_primary_630_2023_11_07|Rare Rainbow|1/78.7|1/78.7402|1/78.7|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|rare||Rare residual|residual|1/1.8212|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh4|regular v|swsh4_digitaltq_primary_630_2023_11_07|Rare Holo V|1/7.9|1/7.8740|1/7.9|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|regular vmax|swsh4_digitaltq_primary_630_2023_11_07|Rare Holo VMAX|1/23.3|1/23.3100|1/23.3|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh4|thepricedex modeled row|swsh4_thepricedex_cross_reference_2026_05|ThePriceDex pull-rate index row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh4|trainer gallery||Trainer Gallery||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh5|alternate art v|battle_styles_community_pack_study|Alt|1/157|1/157|1/157|SOURCE_DIRECT|SOURCE_DIRECT|FIX_RUNTIME_PROBABILITY|
|swsh5|alternate art vmax|battle_styles_community_pack_study|Alt VMAX|1/684|1/684|1/684|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh5|full art|battle_styles_community_pack_study|Full Art|1/56|1/56|1/56|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh5|gold rare|battle_styles_community_pack_study|Gold Rare|1/96|1/96|1/96|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh5|rainbow rare|battle_styles_community_pack_study|Rainbow Rare|1/120|1/120|1/120|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh5|rare||Rare residual|residual|1/2.2360|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh5|regular v|battle_styles_community_pack_study|V|1/7.5|1/7.5000|1/7.5|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh5|regular vmax|battle_styles_thepricedex_cross_reference_2026_05|ThePriceDex Rare Holo VMAX||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh5|regular vstar||VSTAR||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh5|secret rare broad index|battle_styles_thepricedex_cross_reference_2026_05|ThePriceDex Secret Rare||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh5|trainer gallery||Trainer Gallery||||MISSING_SOURCE|MISSING_SOURCE|OK_SOURCE_LOCKED|
|swsh6|alternate art v|charizardx_user_rows|Full Art Alt|1/109|1/109|1/109|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|alternate art vmax|charizardx_user_rows|VMAX Alt|1/396|1/396|1/396|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|full art trainer|charizardx_user_rows|Full Art Trainer|1/74|1/74|1/74|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|full art v|charizardx_user_rows|Full Art V|1/47|1/47|1/47|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|gold rare|charizardx_user_rows|Gold|1/96|1/96|1/96|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|gold secret rare||gold secret rare||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh6|holo rare|dripshop_directional|dripshop_holo_directional|~1/3|1/3|~1/3|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh6|rainbow rare|charizardx_user_rows|Rainbow|1/83|1/83|1/83|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh6|rainbow trainer||rainbow trainer||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh6|rainbow vmax||rainbow vmax||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh6|rare||rare|1/2.39|1/2.3871|1/2.39|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh6|regular v|reddit_directional|reddit_regular_v_directional|~1/7.5|1/7.5000|~1/7.5|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh6|regular vmax|charizardx_user_rows|VMAX|1/22|1/22|1/22|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|alternate art v|tcgplayer_evolving_skies_8000_pack|Alt-Art Pokemon V|1.10%|1/90.9091|1.10%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|alternate art vmax|tcgplayer_evolving_skies_8000_pack|Alt-Art Pokemon VMAX|0.30%|1/333.3333|0.30%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|full art|tcgplayer_evolving_skies_8000_pack|Full-Art|2.78%|1/35.9712|2.78%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|full art trainer||full art trainer||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh7|full art v||full art v||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh7|gold rare|tcgplayer_evolving_skies_8000_pack|Gold Rare|0.91%|1/109.8901|0.91%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|gold secret rare||gold secret rare||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh7|holo rare|dripshop|holo_rare_secondary_directional|~1/3|1/3|~1/3|PROVISIONAL_DIRECTIONAL|PROVISIONAL_DIRECTIONAL|OK_SOURCE_LOCKED|
|swsh7|rainbow rare|tcgplayer_evolving_skies_8000_pack|Rainbow Rare|0.84%|1/119.0476|0.84%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|rainbow trainer||rainbow trainer||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh7|rainbow vmax||rainbow vmax||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|
|swsh7|rare||rare|1/2.24|1/2.2433|1/2.24|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh7|regular v|tcgplayer_evolving_skies_8000_pack|Normal Pokemon V|10.56%|1/9.4697|10.56%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh7|regular vmax|tcgplayer_evolving_skies_8000_pack|Normal Pokemon VMAX|5.60%|1/17.8571|5.60%|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|alt art v|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Alt-Art V|1/180||1/180|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|alt art vmax|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Alt-Art VMAX|1/332||1/332|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|alt v|fusion_strike_reddit_3024_chart_2021_11|Alt V|1/137||1/137|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|alt v or vmax combined|fusion_strike_reddit_3024_chart_2021_11|Alt V or VMAX combined|1/92||1/92|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|alt vmax|fusion_strike_reddit_3024_chart_2021_11|Alt VMAX|1/275||1/275|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|full art pokemon|fusion_strike_reddit_3024_chart_2021_11|Full Art Pokemon|1/66||1/66|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|full art supporter|fusion_strike_reddit_3024_chart_2021_11|Full Art Supporter|1/72||1/72|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|full art trainer|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Full-Art Trainer|1/64||1/64|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|full art v|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Full-Art V|1/58||1/58|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|gold|fusion_strike_reddit_3024_chart_2021_11|Gold|1/116||1/116|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|golden rare|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Golden Rare|1/120||1/120|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|hit rate ultra rare or better|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Hit Rate, Ultra Rare or better|1/5||1/5|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|hits per 36 packs|fusion_strike_reddit_3024_chart_2021_11|Hits per 36 packs|7.92 per 36 packs||7.92 per 36 packs|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|holo vmax|fusion_strike_tcgplayer_instagram_4000plus_2021_11|Holo VMAX|1/30||1/30|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|hyper|fusion_strike_reddit_3024_chart_2021_11|Hyper|1/126||1/126|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|rainbow rare|fusion_strike_thepricedex_cross_reference_2026_05|Rainbow Rare|1/91.9||1/91.9|SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh8|rare holo v|fusion_strike_thepricedex_cross_reference_2026_05|Rare Holo V|1/11.1||1/11.1|SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh8|rare holo vmax|fusion_strike_thepricedex_cross_reference_2026_05|Rare Holo VMAX|1/26.5||1/26.5|SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh8|secret rare|fusion_strike_thepricedex_cross_reference_2026_05|Secret Rare|1/120||1/120|SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh8|ultra rare|fusion_strike_thepricedex_cross_reference_2026_05|Ultra Rare|1/26.0||1/26.0|SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh8|v|fusion_strike_reddit_3024_chart_2021_11|V|1/7.8||1/7.8|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh8|vmax|fusion_strike_reddit_3024_chart_2021_11|VMAX|1/28||1/28|SOURCE_DIRECT|SOURCE_DIRECT|OK_SOURCE_LOCKED|
|swsh9|alternate art v|brilliant_stars_reddit_2160_pack_study_2022_03|Alternate Art V|1/180|1/180|1/180|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|full art|brilliant_stars_reddit_2160_pack_study_2022_03|Full Art|1/62|1/62|1/62|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|gold rare|brilliant_stars_reddit_2160_pack_study_2022_03|Gold Rare|1/120|1/120|1/120|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|rainbow rare|brilliant_stars_reddit_2160_pack_study_2022_03|Rainbow Rare|1/110|1/110|1/110|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|rare||Rare residual|residual|1/2.5729|residual|SOURCE_DERIVED_RESIDUAL|SOURCE_DERIVED_RESIDUAL|OK_SOURCE_LOCKED|
|swsh9|regular v|brilliant_stars_reddit_2160_pack_study_2022_03|V|1/7.2|1/7.2000|1/7.2|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|regular vmax|brilliant_stars_reddit_2160_pack_study_2022_03|VMAX|1/30|1/30|1/30|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|regular vstar|brilliant_stars_reddit_2160_pack_study_2022_03|VSTAR|1/15|1/15|1/15|SOURCE_DIRECT|SOURCE_DIRECT|FIX_SOURCE_URL + PROMOTE_BETTER_PRIMARY_SOURCE|
|swsh9|thepricedex inferred|brilliant_stars_thepricedex_cross_reference_2026_05|ThePriceDex inferred row||||SECONDARY_INDEX_ONLY|SECONDARY_INDEX_ONLY|OK_SOURCE_LOCKED|
|swsh9|trainer gallery||Trainer Gallery||||UNSUPPORTED_SPLIT|UNSUPPORTED_SPLIT|OK_SOURCE_LOCKED|

### 6. Tests
- tests added:
  - test_swsh_config_source_odds_match_runtime_for_all_direct_runtime_rows
  - test_swsh_direct_source_rows_use_specific_non_generic_urls
  - test_swsh5_and_swsh6_known_bad_values_do_not_reappear
  - helper assertions: assert_source_locked_bucket, assert_config_source_odds_match_runtime
- tests updated: swsh5 and swsh6 pull-rate reference tests with strict source-lock expectations
- commands run:
  - python -m pytest backend/tests/unit/db/services/test_explore_page_service.py -k "source_lock or swsh5 or battle_styles or swsh6 or chilling" -vv  -> PASS (14 passed)
  - python -m pytest backend/tests/unit/db/services/test_explore_page_service.py -k "config_source_odds_match_runtime or direct_source_rows_use_specific_non_generic_urls" -vv -> PASS (24 passed)
  - python -m pytest backend/tests -k "source_lock or pull_rate_reference or slot_schema or battle_styles or chilling" -vv -> FAIL (pre-existing broader simulation/runtime failures unrelated to this patch set)
- pass/fail results: focused source-lock tests passed; broad mixed suite not fully green

### 7. Persistence / simulation
- dry-runs run: none
- sets re-simulated: none
- persisted data changed: none
- sets not re-simulated and why: policy gate retained; source and tests were corrected first, and this change set did not execute persistence pipelines

### 8. Guardrail confirmation
- no invented values remain marked direct: confirmed for all direct runtime rows in audited sets
- no generic source URLs remain for direct-source buckets: confirmed by URL guardrail tests
- ThePriceDex is not promoted to direct source unless explicitly approved: confirmed
- source odds match runtime probabilities for all direct buckets: confirmed by config-level guardrail tests
- displayed odds match source-locked values: confirmed for direct runtime rows
- no scoring, RIP, pillar, interpretation, or frontend styling logic changed: confirmed in this patch set
