# Treatment Market Prestige V3 — Round 13 Results

1. **Round 13 study ID:** `"treatment-market-prestige-v3-r13-feaec64cf9c0bb6f"`

2. **Starting coverage:** `{"cards": 9202, "coverage": 0.4636468987756336}`

3. **70% target:** `{"cards": 13893, "coverage": 0.7}`

4. **Exact gap:** `4691`

5. **Functional Trainer preregistered model:** `{"bootstrap_draws": 399, "estimand": "How strongly does the market value a functional Trainer card's treatment package relative to comparable functional Trainer treatments in its era, controlling exactly for canonical functional-card identity and set through within-identity-by-set contrasts?", "frozen_before_coefficients": true, "maximum_90_day_score_drift": 1.0, "maximum_adjacent_score_drift": 0.5, "maximum_loso_shift": 1.0, "maximum_prediction_interval_width": 4.0, "minimum_cards_per_treatment": 25, "minimum_checkpoint_coverage": 0.95, "minimum_checkpoints": 4, "minimum_cross_treatment_identities": 20, "minimum_sets": 3, "minimum_span_days": 85, "minimum_within_identity_set_pairs": 20, "semantics": "TRAINER_SUPERTYPE_RELATIVE_WITHIN_ERA_OR_REGIME"}`

6. **Functional Trainer identification gates:** `{"bootstrap_draws": 399, "estimand": "How strongly does the market value a functional Trainer card's treatment package relative to comparable functional Trainer treatments in its era, controlling exactly for canonical functional-card identity and set through within-identity-by-set contrasts?", "frozen_before_coefficients": true, "maximum_90_day_score_drift": 1.0, "maximum_adjacent_score_drift": 0.5, "maximum_loso_shift": 1.0, "maximum_prediction_interval_width": 4.0, "minimum_cards_per_treatment": 25, "minimum_checkpoint_coverage": 0.95, "minimum_checkpoints": 4, "minimum_cross_treatment_identities": 20, "minimum_sets": 3, "minimum_span_days": 85, "minimum_within_identity_set_pairs": 20, "semantics": "TRAINER_SUPERTYPE_RELATIVE_WITHIN_ERA_OR_REGIME"}`

7. **Functional Trainer pilot results:** `[{"comparisonUniverse": "TRAINER_SUPERTYPE_RELATIVE_WITHIN_ERA", "design": {"checkpoints": 4, "crossTreatmentIdentities": 40, "sets": 13, "treatmentCounts": {"rare_secret": 47, "uncommon": 93}, "withinIdentitySetPairs": 40}, "domain": "ITEM", "era": "Sun and Moon", "gates": {"cards": true, "history": true, "identities": true, "pairs": true, "sets": true}, "heterogeneityPass": true, "recoverableCards": 140, "series": [{"coverage": 1.0, "date": "2026-05-31", "model": {"betweenSetVariance": 0.05642899399297545, "difference": 3.433801736934992, "maximumLosoShift": 0.018354232576284435, "pairCount": 40, "predictionIntervals": {"rare_secret": [5.8427904624139675, 6.122242312401185], "uncommon": [3.8777576875988156, 4.1572095375860325]}, "scoreIntervals": {"rare_secret": [5.9264768726936135, 6.03462811175487], "uncommon": [3.96537188824513, 4.0735231273063865]}, "scores": {"rare_secret": 5.9837940046494875, "uncommon": 4.0162059953505125}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-06-30", "model": {"betweenSetVariance": 0.034676366148822545, "difference": 3.4776320936184844, "maximumLosoShift": 0.014507741070859836, "pairCount": 40, "predictionIntervals": {"rare_secret": [5.8829494964231435, 6.107043167201841], "uncommon": [3.892956832798159, 4.1170505035768565]}, "scoreIntervals": {"rare_secret": [5.928525910010528, 6.0361456566728195], "uncommon": [3.9638543433271805, 4.071474089989472]}, "scores": {"rare_secret": 5.9958292989936535, "uncommon": 4.0041707010063465}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-07-30", "model": {"betweenSetVariance": 0.040443499436462534, "difference": 3.4550828615686426, "maximumLosoShift": 0.01889904187390945, "pairCount": 40, "predictionIntervals": {"rare_secret": [5.8671262206541455, 6.11020723653954], "uncommon": [3.889792763460459, 4.132873779345855]}, "scoreIntervals": {"rare_secret": [5.923336552901013, 6.034936226346367], "uncommon": [3.9650637736536343, 4.076663447098988]}, "scores": {"rare_secret": 5.9896399324231435, "uncommon": 4.0103600675768565}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-08-29", "model": {"betweenSetVariance": 0.039186620147928154, "difference": 3.4196580228148297, "maximumLosoShift": 0.023250282050960358, "pairCount": 40, "predictionIntervals": {"rare_secret": [5.857783813433772, 6.100115714935719], "uncommon": [3.8998842850642808, 4.142216186566229]}, "scoreIntervals": {"rare_secret": [5.923192895888184, 6.024798955261129], "uncommon": [3.975201044738871, 4.076807104111817]}, "scores": {"rare_secret": 5.979906246752941, "uncommon": 4.020093753247059}, "setCount": 13}}], "status": "AVAILABLE", "temporal": {"rare_secret": {"maximumAdjacentDrift": 0.012035294344165948, "ninetyDayDrift": 0.0038877578965461623}, "uncommon": {"maximumAdjacentDrift": 0.012035294344165948, "ninetyDayDrift": 0.0038877578965461623}}}, {"comparisonUniverse": "TRAINER_SUPERTYPE_RELATIVE_WITHIN_ERA", "design": {"checkpoints": 4, "crossTreatmentIdentities": 22, "sets": 13, "treatmentCounts": {"rare_secret": 27, "uncommon": 116}, "withinIdentitySetPairs": 22}, "domain": "ITEM", "era": "Sword and Shield", "gates": {"cards": true, "history": true, "identities": true, "pairs": true, "sets": true}, "heterogeneityPass": true, "recoverableCards": 143, "series": [{"coverage": 1.0, "date": "2026-05-31", "model": {"betweenSetVariance": 0.01571652399790672, "difference": 3.35216835034142, "maximumLosoShift": 0.07686532144818337, "pairCount": 22, "predictionIntervals": {"rare_secret": [7.581547757654007, 7.903816337313136], "uncommon": [2.0961836626868644, 2.4184522423459933]}, "scoreIntervals": {"rare_secret": [7.64872026897254, 7.841240892876591], "uncommon": [2.158759107123409, 2.351279731027459]}, "scores": {"rare_secret": 7.7511309072667345, "uncommon": 2.2488690927332646}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-06-30", "model": {"betweenSetVariance": 0.0, "difference": 3.348213504525487, "maximumLosoShift": 0.00763814608743596, "pairCount": 22, "predictionIntervals": {"rare_secret": [7.697650463867086, 7.79874857934811], "uncommon": [2.2012514206518903, 2.3023495361329145]}, "scoreIntervals": {"rare_secret": [7.651876237409539, 7.856036041762622], "uncommon": [2.1439639582373777, 2.348123762590461]}, "scores": {"rare_secret": 7.749031285989642, "uncommon": 2.2509687140103583}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-07-30", "model": {"betweenSetVariance": 0.12725226544061513, "difference": 3.2753392238002323, "maximumLosoShift": 0.06773307267381679, "pairCount": 22, "predictionIntervals": {"rare_secret": [7.226588108248845, 8.080824782949158], "uncommon": [1.9191752170508418, 2.773411891751156]}, "scoreIntervals": {"rare_secret": [7.484786420816495, 7.918777371842658], "uncommon": [2.081222628157342, 2.515213579183504]}, "scores": {"rare_secret": 7.709826146931409, "uncommon": 2.2901738530685907}, "setCount": 13}}, {"coverage": 1.0, "date": "2026-08-29", "model": {"betweenSetVariance": 0.09378288418145146, "difference": 3.103643892269534, "maximumLosoShift": 0.031796914615527694, "pairCount": 22, "predictionIntervals": {"rare_secret": [7.186560370812449, 7.956935820374611], "uncommon": [2.043064179625389, 2.8134396291875508]}, "scoreIntervals": {"rare_secret": [7.362511351702377, 7.703060702965169], "uncommon": [2.2969392970348306, 2.637488648297623]}, "scores": {"rare_secret": 7.6135397869042825, "uncommon": 2.386460213095718}, "setCount": 13}}], "status": "AVAILABLE", "temporal": {"rare_secret": {"maximumAdjacentDrift": 0.09628636002712643, "ninetyDayDrift": 0.13759112036245202}, "uncommon": {"maximumAdjacentDrift": 0.09628636002712732, "ninetyDayDrift": 0.13759112036245336}}}]`

8. **Functional Trainer temporal results:** `{"Sun and Moon": {"rare_secret": {"maximumAdjacentDrift": 0.012035294344165948, "ninetyDayDrift": 0.0038877578965461623}, "uncommon": {"maximumAdjacentDrift": 0.012035294344165948, "ninetyDayDrift": 0.0038877578965461623}}, "Sword and Shield": {"rare_secret": {"maximumAdjacentDrift": 0.09628636002712643, "ninetyDayDrift": 0.13759112036245202}, "uncommon": {"maximumAdjacentDrift": 0.09628636002712732, "ninetyDayDrift": 0.13759112036245336}}}`

9. **Functional Trainer recoverable cards:** `283`

10. **Supporter identity ontology result:** `{"AMBIGUOUS": 1132, "CANONICAL_CARD_FAMILY_IDENTITY": 0, "CANONICAL_CHARACTER_IDENTITY": 0, "GENERIC_ROLE_IDENTITY": 0, "NO_SAFE_IDENTITY": 0}`

11. **Supporter safe identity count:** `0`

12. **Supporter cross-treatment identity count:** `0`

13. **Supporter model feasibility:** `"SUPPORTER_V3_REQUIRES_EXTERNAL_IDENTITY_DATA"`

14. **Supporter potential recovery:** `0`

15. **E-Card missing-history root cause:** `{"HISTORICAL_OBSERVATIONS_NEVER_RETAINED": 273, "INCOMPLETE_SOURCE_INGESTION": 155, "PRICE_CONDITION_MISMATCH": 26}`

16. **E-Card repaired history coverage:** `0.6265060240963856`

17. **E-Card model result:** `"NOT_RUN_HISTORY_BELOW_GATE"`

18. **E-Card recoverable cards:** `0`

19. **Base/WOTC structural decomposition:** `{"architecture": "ERA_RELATIVE; price-blind Jaccard rule yields no valid >=3-set boundary. Base Set 2 alone cannot form a regime.", "editionMix": {"1st_edition": 100, "__UNMAPPED__": 231, "unlimited": 110}, "finishMix": {"holo": 85, "non_holo": 356}, "sets": {"Base": 102, "Base Set 2": 130, "Fossil": 62, "Jungle": 64, "Team Rocket": 83}}`

20. **Base/WOTC treatment universes:** `["common", "rare", "rare_holo", "uncommon"]`

21. **Base/WOTC temporal failure causes:** `["genuine checkpoint score drift under current universe", "edition-status mixture is canonical but not represented in rarity-only treatment identity", "only one eligible treatment leaves insufficient universe support"]`

22. **Base/WOTC pilot results:** `"PRESERVED_ROUND12_FAIL_CLOSED"`

23. **Base/WOTC recoverable cards:** `0`

24. **POP result:** `{"cards": 153, "eligiblePokemonCards": 135, "nearTieRule": "already similarity-aware; not causal", "recoverableCards": 0, "status": "INSUFFICIENT_ERA_SUPPORT", "treatments": {"common": "AVAILABLE", "rare": "MODEL_INSTABILITY", "uncommon": "MODEL_INSTABILITY"}}`

25. **POP recoverable cards:** `0`

26. **Gym status and card count:** `{"cards": 265, "eligiblePokemonCards": 186, "sets": 2, "status": "INSUFFICIENT_MULTI_SET_SUPPORT"}`

27. **NP status and card count:** `{"cards": 74, "cause": "single promo set; promo ambiguity removes the canonical eligible cohort; no multi-treatment, multi-set comparison", "eligiblePokemonCards": 0, "status": "INSUFFICIENT_TREATMENT_SUPPORT"}`

28. **Other decomposition:** `{"assessment": "Artificial miscellaneous catalog bucket mixing Legendary Collection, Southern Islands, Pok\u00e9mon Rumble, and unrelated McDonald's releases; no safe cross-set comparison universe.", "cards": 271, "recoverableCards": 0, "safeReassignments": 0, "sets": {"Legendary Collection": 110, "McDonald's Collection 2011": 12, "McDonald's Collection 2012": 12, "McDonald's Collection 2014": 12, "McDonald's Collection 2015": 12, "McDonald's Collection 2016": 6, "McDonald's Collection 2017": 12, "McDonald's Collection 2018": 12, "McDonald's Collection 2019": 12, "McDonald's Collection 2021": 25, "McDonald's Collection 2022": 15, "Pok\u00e9mon Rumble": 13, "Southern Islands": 18}}`

29. **Other recoverable cards:** `0`

30. **Any legitimately recovered instability cards:** `0`

31. **Energy status:** `{"cards": 371, "lowCostSubclassFound": false, "status": "ENERGY_V3_ESTIMAND_REQUIRES_MORE_DATA"}`

32. **Pokémon-domain coverage:** `{"cards": 9202, "coverage": 0.559086214229297, "denominator": 16459}`

33. **Trainer-domain coverage:** `{"cards": 283, "coverage": 0.10412067696835908, "denominator": 2718}`

34. **Catalog-wide likely coverage:** `{"cards": 9485, "coverage": 0.4779059807527586, "denominator": 19847}`

35. **Conservative coverage:** `{"cards": 9202, "coverage": 0.4636468987756336}`

36. **Optimistic defensible coverage:** `{"cards": 9485, "coverage": 0.4779059807527586}`

37. **Remaining cards to 70%:** `4408`

38. **Minimum project set for 70%:** `{"conservative": null, "likely": null, "optimisticDefensible": null, "reason": "All named downstream-valid and bounded plausible projects remain below 13,893."}`

39. **80% feasibility:** `"NOT_FEASIBLE_FROM_CURRENT_NAMED_PROJECTS"`

40. **Trainer decision:** `"FUNCTIONAL_TRAINER_V3_PARTIALLY_VALIDATED"`

41. **E-Card decision:** `"ECARD_RETENTION_REPAIR_REQUIRED"`

42. **Base/WOTC decision:** `"BASE_WOTC_RECOVERY_LOW_VALUE"`

43. **70% decision:** `"70_PERCENT_PATH_REMAINS_UNPROVEN"`

44. **Whether production remains paused:** `true`

45. **Rows persisted:** `0`

46. **Production behavior:** `"Research-only; no migrations, approved candidates, production score rows, UI/Card Detail, V1/V2, appeal, RIP, or ranking changes."`

47. **Files changed:** `["backend/scripts/audit_treatment_market_prestige_v3_round13_ecard.py", "backend/scripts/build_treatment_market_prestige_v3_round13.py", "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round13.py", "docs\\research\\treatment_market_prestige_v3_round13_ecard_retention_audit.json", "docs\\research\\treatment_market_prestige_v3_round13_study.json", "docs\\research\\TREATMENT_MARKET_PRESTIGE_V3_ROUND13_RESULTS.md", "docs\\research\\treatment_market_prestige_v3_round13_closure\\manifest.json"]`

48. **Tests executed:** `["functional Trainer preregistration/design gates", "paired identity\u00d7set temporal pilots", "E-Card retention audit", "older-era fail-closed decomposition", "coverage mathematics", "full V3 regression"]`

49. **Remaining limitations:** `["Supporter character identity metadata is absent", "only two functional Item universes pass identification gates", "E-Card missing checkpoint prices cannot be reconstructed", "Base/WOTC edition-aware ontology is unresolved", "research-supported coverage is not production approval"]`

50. **Exact next task:** `"Round 14 should not resume production: build an authoritative Supporter character identity source or import one with provenance, repair E-Card checkpoint ingestion from source evidence, and resolve modern unsupported SWSH/S&M treatment regimes; the current named projects do not reach 70%."`
