# Treatment Market Prestige V3 — Round 17 Results

1. **branch:** `"fix/public-rankings-entitlement-regression"`

2. **HEAD:** `"034f42f0e92ccda582699bb6bca7e87b3b96a8d0"`

3. **frozen residual count:** `8480`

4. **residual integrity check:** `{"actual": 8480, "allInLedger": true, "allUnresolved": true, "excludedProtectedStates": true, "expected": 8480, "unique": 8480}`

5. **empirical anchor count:** `38`

6. **treatment anchor count:** `34`

7. **structural similarity features:** `["normalized treatment designation tokens", "regular versus premium family", "holo/finish semantics", "full-art/illustration semantics", "secret-number semantics", "rainbow/gold/shiny/radiant/gallery semantics", "mechanic/form tokens", "edition status", "special treatment", "promo/special-release status", "same regime", "same era", "explicit adjacent-era lineage", "authoritative pull-scarcity band (comparison only)"]`

8. **candidate algorithms:** `["NEAREST", "BOUNDED_INTERPOLATION", "WEIGHTED_NEIGHBORS", "HIERARCHICAL_ERA_REGIME"]`

9. **preregistered holdout gates:** `{"highConfidenceMaximumCalibratedMAE": 0.75, "maximumMAE": 1.0, "maximumP90AbsoluteError": 2.0, "minimumOrderingAccuracy": 0.65, "minimumPredictedHoldouts": 20, "minimumSpearman": 0.5, "moderateConfidenceMaximumCalibratedMAE": 1.25, "publicationPolicy": "High and moderate require their confidence-class holdout error gates; low remains diagnostic."}`

10. **leave-treatment-out results:** `{"mae": 0.837101015602775, "maximumAbsoluteError": 2.694955478450826, "medianAbsoluteError": 0.6878076961767632, "n": 32, "orderingAccuracy": 0.4198782961460446, "p90AbsoluteError": 1.6661911658520874, "rmse": 1.0471478361093265, "scoreTierAgreement": 0.71875, "spearman": -0.24605795567111782}`

11. **era/regime holdout results:** `{}`

12. **MAE:** `0.837101015602775`

13. **median absolute error:** `0.6878076961767632`

14. **RMSE:** `1.0471478361093265`

15. **p90 absolute error:** `1.6661911658520874`

16. **maximum error:** `2.694955478450826`

17. **rank correlation:** `-0.24605795567111782`

18. **ordering accuracy:** `0.4198782961460446`

19. **confidence calibration:** `{"HIGH": {"mae": 1.0979504718486628, "maximumAbsoluteError": 1.4725675064682342, "medianAbsoluteError": 1.0979504718486628, "n": 2, "orderingAccuracy": 0.0, "p90AbsoluteError": 1.39764409954432, "rmse": 1.1601004961898183, "scoreTierAgreement": 0.5, "spearman": -1.0}, "LOW": {"mae": 0.837101015602775, "maximumAbsoluteError": 2.694955478450826, "medianAbsoluteError": 0.6878076961767632, "n": 32, "orderingAccuracy": 0.4198782961460446, "p90AbsoluteError": 1.6661911658520874, "rmse": 1.0471478361093265, "scoreTierAgreement": 0.71875, "spearman": -0.24605795567111782}, "MODERATE": {"mae": 0.8537252823139294, "maximumAbsoluteError": 2.694955478450826, "medianAbsoluteError": 0.7233334372290914, "n": 31, "orderingAccuracy": 0.4134199134199134, "p90AbsoluteError": 1.687704905783626, "rmse": 1.0623326835217732, "scoreTierAgreement": 0.7096774193548387, "spearman": -0.260185579862014}}`

20. **selected inference algorithm:** `null`

21. **scarcity/no-scarcity comparison:** `{"withBounded": {"mae": 0.8376156750948434, "maximumAbsoluteError": 2.694955478450826, "medianAbsoluteError": 0.6874274252521624, "n": 32, "orderingAccuracy": 0.4198782961460446, "p90AbsoluteError": 1.666029784152522, "rmse": 1.047254530994436, "scoreTierAgreement": 0.71875, "spearman": -0.24605795567111782}, "without": {"mae": 0.837101015602775, "maximumAbsoluteError": 2.694955478450826, "medianAbsoluteError": 0.6878076961767632, "n": 32, "orderingAccuracy": 0.4198782961460446, "p90AbsoluteError": 1.6661911658520874, "rmse": 1.0471478361093265, "scoreTierAgreement": 0.71875, "spearman": -0.24605795567111782}}`

22. **selected scarcity policy:** `"NO_SCARCITY"`

23. **Trainer inference handling:** `"Normal treatment framework allowed after Trainer-specific precedence; functional identity not required."`

24. **Energy handling:** `"NEUTRAL_TREATMENT=0.0; excluded from frozen inference."`

25. **promo handling:** `"Require same-regime defensible printing analog; unique promo mechanics abstain."`

26. **Base/WOTC handling:** `"Edition and finish required; no rarity-only collapse."`

27. **special-release handling:** `"Round 16 taxonomy retained; no artificial Other universe."`

28. **high-confidence inferred treatment buckets:** `0`

29. **high-confidence inferred cards:** `0`

30. **moderate-confidence inferred treatment buckets:** `0`

31. **moderate-confidence inferred cards:** `0`

32. **low-confidence candidates:** `5531`

33. **unresolved cards:** `8480`

34. **unresolved by era:** `{"Base/WOTC": 297, "Black and White": 275, "Diamond and Pearl": 110, "E-Card": 502, "EX": 32, "Gym": 253, "HeartGold and SoulSilver": 106, "Mega Evolution": 893, "NP": 74, "Neo": 216, "Other": 269, "POP": 94, "Platinum": 161, "Scarlet and Violet": 226, "Sun and Moon": 1269, "Sword and Shield": 2717, "XY": 986}`

35. **unresolved by treatment:** `{"__UNMAPPED__": 202, "ace_spec_rare": 30, "amazing_rare": 9, "black_white_rare": 2, "classic_collection": 25, "common": 2239, "holo_rare": 16, "hyper_rare": 62, "illustration_rare": 101, "legend": 18, "mega_attack_rare": 7, "mega_hyper_rare": 8, "promo": 764, "radiant_rare": 15, "rare": 908, "rare_ace": 13, "rare_holo": 630, "rare_holo_ex": 56, "rare_holo_gx": 56, "rare_holo_lv_x": 30, "rare_holo_star": 14, "rare_holo_v": 204, "rare_holo_vmax": 77, "rare_holo_vstar": 43, "rare_prism_star": 25, "rare_rainbow": 142, "rare_secret": 213, "rare_shining": 15, "rare_shiny": 149, "rare_shiny_gx": 35, "rare_ultra": 317, "secret_rare": 2, "shiny_rare": 120, "shiny_ultra_rare": 12, "special_illustration_rare": 55, "trainer_gallery_rare_holo": 80, "ultra_rare": 111, "uncommon": 1675}`

36. **unresolved by blocker:** `{"BASE_WOTC_EDITION_FINISH_INCOMPLETE": 145, "LOW_CONFIDENCE_NOT_PUBLISHABLE": 5531, "MISSING_NORMALIZED_TREATMENT": 202, "NO_DEFENSIBLE_EMPIRICAL_ANCHOR": 1837, "PROMO_ANALOG_NOT_DEFENSIBLE": 765}`

37. **empirical coverage:** `{"cards": 10996, "coverage": 0.554038393711896}`

38. **neutral coverage:** `{"cards": 371, "coverage": 0.018693001461178013}`

39. **high-confidence inferred coverage:** `{"cards": 0, "coverage": 0.0}`

40. **moderate-confidence inferred coverage:** `{"cards": 0, "coverage": 0.0}`

41. **conservative usable coverage:** `{"cards": 11367, "coverage": 0.572731395173074}`

42. **broad defensible usable coverage:** `{"cards": 11367, "coverage": 0.572731395173074}`

43. **remaining null coverage:** `{"cards": 8480, "coverage": 0.42726860482692597}`

44. **methodology disclosure draft:** `"Treatment Market Prestige uses direct market evidence wherever sufficient historical comparisons exist. For treatments too sparse for standalone estimation, inDex may use a validated best-fit estimate based on the nearest empirically supported treatment structures in the same era or regime. Inferred scores are tracked separately from directly measured scores."`

45. **info-bubble draft:** `"Some sparse treatments use a separately labeled, holdout-validated estimate from nearby empirical treatment structures; they are not direct measurements."`

46. **Collector Appeal integration warning:** `"Do not integrate in Round 17. A future study must separately test direct-only, direct plus high-confidence inference, confidence weighting, and exclusion of inferred TMP; it must not assume equal confidence or choose a weight here."`

47. **best-fit framework decision:** `"BEST_FIT_FRAMEWORK_NOT_SUPPORTED"`

48. **scarcity decision:** `"BEST_FIT_SCARCITY_REDUNDANT"`

49. **high-confidence decision:** `"HIGH_CONFIDENCE_BEST_FIT_NOT_VALIDATED"`

50. **moderate-confidence decision:** `"MODERATE_CONFIDENCE_BEST_FIT_NOT_VALIDATED"`

51. **coverage decision:** `"BEST_FIT_COVERAGE_LIMITED"`

52. **production pause:** `true`

53. **rows persisted:** `0`

54. **files changed:** `["D:\\EVRCalculator\\backend\\scripts\\build_treatment_market_prestige_v3_round17.py", "docs\\research\\treatment_market_prestige_v3_round17_study.json", "docs\\research\\TREATMENT_MARKET_PRESTIGE_V3_ROUND17_RESULTS.md", "docs\\research\\treatment_market_prestige_v3_round17\\empirical_anchor_graph.json", "docs\\research\\treatment_market_prestige_v3_round17\\holdout_validation.json", "docs\\research\\treatment_market_prestige_v3_round17\\card_level_best_fit.json", "docs\\research\\treatment_market_prestige_v3_round17\\low_confidence_candidates.json", "docs\\research\\treatment_market_prestige_v3_round17\\unresolved_population.json", "docs\\research\\treatment_market_prestige_v3_round17\\manifest.json"]`

55. **tests executed:** `["Round 17 focused: 4 passed in 2.72s", "Combined V3/Supporter/Trainer regression: 75 passed, 1785 deselected in 80.54s"]`

56. **reproducibility checks:** `{"anchorGraphHash": "3c1ce6d633378cf5f167a598992a9d8a374885af4f44cbca8aff667380c9a50a", "deterministic": true, "frozenPopulationHash": "d22a2b0714a460fdde3d59c6f1a51011be113829035830b2389c510e7444dac4", "priceFeatureUsed": false}`

57. **limitations:** `["Only 38 distinct empirical anchors are available", "holdout performance measures structural reconstruction, not causal identification", "scarcity availability is incomplete", "cross-era inference is limited to explicit adjacent-era family continuity", "low-confidence candidates remain unpublished"]`

58. **exact recommended next action:** `"If a confidence class passes preregistered holdout gates, independently review its treatment-bucket assignments before any production implementation; otherwise acquire new historical treatment evidence."`
