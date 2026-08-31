# Treatment Market Prestige V3 — Round 20 Results

1. **branch:** `"fix/public-rankings-entitlement-regression"`

2. **HEAD:** `"35a41224661b243cccef81f71cb2dacfc4426951"`

3. **Round 20 study ID:** `"treatment-market-prestige-v3-r20-75c3898bfc2efe3c"`

4. **frozen empirical anchors:** `38`

5. **distinct treatment anchors:** `34`

6. **targeted structural cards:** `2044`

7. **structural treatment buckets:** `105`

8. **fingerprint features:** `["treatment family", "holo/non-holo finish", "texture/special finish", "full-art", "illustration", "special illustration", "rainbow", "gold/secret numbering", "shiny", "radiant", "gallery/subset", "mechanic family (EX/GX/V/VMAX/VSTAR/ex/Mega/LV.X/Prime/Star/Shining)", "edition", "special release", "card/set support", "treatment lifespan proxy", "authoritative exact-pull probability", "within-era relative pull percentile", "derived hit-frequency band", "pack-slot architecture when authoritative"]`

9. **feature provenance:** `{"TMP": "Round 15 direct empirical matrix", "canonical": "Round 5 frozen cohort", "packArchitecture": "unavailable where not explicitly frozen", "pull": "exact_pull_probability only"}`

10. **pull-rate coverage:** `{"anchorCardsWeightedCoverage": 0.401521659099276, "anchorNodes": 8, "candidateNodes": 13}`

11. **relative hit-position methodology:** `"Within each era, rank only treatments with authoritative median exact-pull probability; map percentile thirds to derived frequent/mid/scarce bands. Missing odds remain unavailable."`

12. **structural similarity methodology:** `"Price-free weighted agreement over family, visual flags, finish, mechanic context, historical set support, and optional authoritative scarcity; treatment strings are not directly matched."`

13. **analogue graph size:** `{"edges": 501, "nodes": 34}`

14. **candidate algorithms:** `["STRUCTURAL_NEAREST", "WEIGHTED_STRUCTURAL", "STRUCTURAL_PULL", "HIERARCHICAL_FAMILY", "STRUCTURAL_INTERVAL"]`

15. **preregistered gates:** `{"definedBeforeTargetRecoveryInspection": true, "maximumEraMAE": 1.5, "maximumMAE": 0.65, "maximumMedianAbsoluteError": 0.55, "maximumP90AbsoluteError": 1.4, "minimumKendall": 0.45, "minimumOrderingAccuracy": 0.7, "minimumPredictions": 20, "minimumSpearman": 0.65}`

16. **Round 17 baseline:** `{"mae": 0.8104, "maximumAbsoluteError": 2.5999, "medianAbsoluteError": 0.706, "orderingAccuracy": 0.4909, "p90AbsoluteError": 1.7308, "rmse": 1.0671, "spearman": 0.0636}`

17. **leave-treatment-out MAE:** `0.7573079803843334`

18. **leave-treatment-out median AE:** `0.568178670579536`

19. **RMSE:** `1.0093065105305408`

20. **P75 AE:** `1.0796981841379423`

21. **P90 AE:** `1.8587248475019424`

22. **maximum AE:** `2.4362595959665496`

23. **Spearman:** `-0.03851738733254347`

24. **Kendall:** `-0.04847396768402154`

25. **ordering accuracy:** `0.47491039426523296`

26. **premium-only holdout results:** `{"kendall": -0.18181818181818182, "mae": 1.1004507743451144, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.8748555118497476, "n": 10, "orderingAccuracy": 0.4090909090909091, "p75AbsoluteError": 1.8645942173553907, "p90AbsoluteError": 2.036081640138068, "positionAccuracy": 0.7, "rmse": 1.3724123036463398, "spearman": -0.2553203283456271}`

27. **cross-era-only holdout results:** `{"kendall": -0.04847396768402154, "mae": 0.7573079803843334, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.568178670579536, "n": 34, "orderingAccuracy": 0.47491039426523296, "p75AbsoluteError": 1.0796981841379423, "p90AbsoluteError": 1.8587248475019424, "positionAccuracy": 0.7352941176470589, "rmse": 1.0093065105305408, "spearman": -0.03851738733254347}`

28. **leave-era-out results:** `{"kendall": -0.04847396768402154, "mae": 0.7573079803843334, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.568178670579536, "n": 34, "orderingAccuracy": 0.47491039426523296, "p75AbsoluteError": 1.0796981841379423, "p90AbsoluteError": 1.8587248475019424, "positionAccuracy": 0.7352941176470589, "rmse": 1.0093065105305408, "spearman": -0.03851738733254347}`

29. **structure-only result:** `{"kendall": -0.07001795332136446, "mae": 0.7801456458785166, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.6067048819314653, "n": 34, "orderingAccuracy": 0.46415770609318996, "p75AbsoluteError": 1.0855110448169178, "p90AbsoluteError": 1.962314515963444, "positionAccuracy": 0.7058823529411765, "rmse": 1.0430204921968969, "spearman": -0.058998855199848335}`

30. **structure + exact scarcity result:** `{"kendall": -0.059245960502693, "mae": 0.7665172127355301, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.6067048819314653, "n": 34, "orderingAccuracy": 0.46953405017921146, "p75AbsoluteError": 1.058973752491593, "p90AbsoluteError": 1.962314515963444, "positionAccuracy": 0.7352941176470589, "rmse": 1.027900720315487, "spearman": -0.04035154863409316}`

31. **structure + relative scarcity result:** `{"kendall": -0.059245960502693, "mae": 0.7701643866711281, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.576950111356128, "n": 34, "orderingAccuracy": 0.46953405017921146, "p75AbsoluteError": 1.0855110448169178, "p90AbsoluteError": 1.8587248475019424, "positionAccuracy": 0.7058823529411765, "rmse": 1.024585671347552, "spearman": -0.05227359709416614}`

32. **structure + hit-band result:** `{"kendall": -0.04847396768402154, "mae": 0.7573079803843334, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.568178670579536, "n": 34, "orderingAccuracy": 0.47491039426523296, "p75AbsoluteError": 1.0796981841379423, "p90AbsoluteError": 1.8587248475019424, "positionAccuracy": 0.7352941176470589, "rmse": 1.0093065105305408, "spearman": -0.03851738733254347}`

33. **scarcity ablation decision:** `"STRUCTURAL_SCARCITY_SIGNAL_REDUNDANT"`

34. **selected algorithm:** `null`

35. **confidence calibration:** `{"MODERATE": {"kendall": 1.0, "mae": 1.4288062632543599, "maximumAbsoluteError": 1.7765536695536701, "medianAbsoluteError": 1.4288062632543599, "n": 2, "orderingAccuracy": 1.0, "p75AbsoluteError": 1.602679966404015, "p90AbsoluteError": 1.707004188293808, "positionAccuracy": 0.5, "rmse": 1.4705154186552363, "spearman": 1.0}, "STRONG": {"kendall": 0.008130081300813009, "mae": 0.7153393377049568, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.4956838854812977, "n": 32, "orderingAccuracy": 0.5030425963488844, "p75AbsoluteError": 0.990684660870549, "p90AbsoluteError": 1.8454917574339247, "positionAccuracy": 0.75, "rmse": 0.973250936002823, "spearman": 0.04015769841094953}, "WEAK": {"n": 0}}`

36. **high-confidence error:** `{"kendall": 0.008130081300813009, "mae": 0.7153393377049568, "maximumAbsoluteError": 2.4362595959665496, "medianAbsoluteError": 0.4956838854812977, "n": 32, "orderingAccuracy": 0.5030425963488844, "p75AbsoluteError": 0.990684660870549, "p90AbsoluteError": 1.8454917574339247, "positionAccuracy": 0.75, "rmse": 0.973250936002823, "spearman": 0.04015769841094953}`

37. **moderate-confidence error:** `{"kendall": 1.0, "mae": 1.4288062632543599, "maximumAbsoluteError": 1.7765536695536701, "medianAbsoluteError": 1.4288062632543599, "n": 2, "orderingAccuracy": 1.0, "p75AbsoluteError": 1.602679966404015, "p90AbsoluteError": 1.707004188293808, "positionAccuracy": 0.5, "rmse": 1.4705154186552363, "spearman": 1.0}`

38. **structural transfer decision:** `"CROSS_ERA_STRUCTURAL_INFERENCE_NOT_SUPPORTED"`

39. **ranking decision:** `"STRUCTURAL_ORDERING_NOT_VALIDATED"`

40. **cards with 3+ strong analogues:** `975`

41. **cards with 2 analogues:** `336`

42. **cards with 1 analogue:** `58`

43. **cards with no analogue:** `675`

44. **high-confidence inferred treatments if validated:** `0`

45. **high-confidence inferred cards if validated:** `0`

46. **moderate-confidence inferred treatments if validated:** `0`

47. **moderate-confidence inferred cards if validated:** `0`

48. **unresolved targeted cards:** `2044`

49. **collector-relevant usable coverage:** `{"cards": 2807, "coverage": 0.5423106646058733}`

50. **premium usable coverage:** `{"cards": 2395, "coverage": 0.530571555161719}`

51. **collector direct empirical coverage:** `0.5423106646058733`

52. **premium direct empirical coverage:** `0.530571555161719`

53. **collector gap to 70% usable:** `817`

54. **premium gap to 70% usable:** `765`

55. **Top 10 diagnostic before/after:** `{"after": {"cards": 1646, "coverage": 0.43013365735115433, "covered": 708}, "before": {"cards": 1646, "coverage": 0.43013365735115433, "covered": 708}}`

56. **Top 25 diagnostic before/after:** `{"after": {"cards": 3903, "coverage": 0.5221624391493723, "covered": 2038}, "before": {"cards": 3903, "coverage": 0.5221624391493723, "covered": 2038}}`

57. **50%-value diagnostic before/after:** `{"after": {"cards": 831, "coverage": 0.4151624548736462, "covered": 345}, "before": {"cards": 831, "coverage": 0.4151624548736462, "covered": 345}}`

58. **80%-value diagnostic before/after:** `{"after": {"cards": 2557, "coverage": 0.456394211967149, "covered": 1167}, "before": {"cards": 2557, "coverage": 0.456394211967149, "covered": 1167}}`

59. **case-study results:** `[{"analogues": [{"anchor": "Platinum|Platinum_r1|common", "shared": {"family": 1.0, "finish": 1.0, "historicalRole": 0.25, "mechanic": 0.3333333333333333, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarity": 0.8233333333333335}, {"anchor": "Diamond and Pearl|Diamond and Pearl_r1|common", "shared": {"family": 1.0, "finish": 1.0, "historicalRole": 0.14285714285714285, "mechanic": 0.3333333333333333, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarity": 0.8104761904761906}, {"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|uncommon", "shared": {"family": 1.0, "finish": 1.0, "historicalRole": 0.2, "mechanic": 0.2, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarity": 0.8000000000000002}], "candidate": "Mega Evolution|Mega Evolution|common|Trainer", "case": "modern sparse", "result": "UNRESOLVED"}, {"analogues": [{"anchor": "Scarlet and Violet|Scarlet and Violet|special_illustration_rare", "shared": {"family": 1.0, "finish": 1.0, "historicalRole": 0.375, "mechanic": 0.6666666666666666, "packPosition": null, "pullPosition": 1.0, "visual": 1.0}, "similarity": 0.8994166666666668}, {"anchor": "Scarlet and Violet|Scarlet and Violet|illustration_rare", "shared": {"family": 1.0, "finish": 1.0, "historicalRole": 0.4, "mechanic": 0.6, "packPosition": null, "pullPosition": 1.0, "visual": 1.0}, "similarity": 0.8946000000000001}, {"anchor": "Diamond and Pearl|Diamond and Pearl_r1|rare_holo", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.8571428571428571, "mechanic": 0.6, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.5613834586466165}], "candidate": "Mega Evolution|Mega Evolution|special_illustration_rare|Pok\u00e9mon", "case": "gallery/subset", "result": "UNRESOLVED"}, {"analogues": [{"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|common", "shared": {"family": 0.0, "finish": 0.5, "historicalRole": 0.4, "mechanic": 1.0, "packPosition": null, "pullPosition": null, "visual": 0.9473684210526315}, "similarity": 0.5082631578947369}, {"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|rare_prime", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.5, "mechanic": 0.3333333333333333, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.48385964912280705}, {"anchor": "Platinum|Platinum_r1|rare_holo", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.5, "mechanic": 0.3333333333333333, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.48385964912280705}], "candidate": "Neo|Neo|rare_shining|Pok\u00e9mon", "case": "shiny/radiant", "result": "UNRESOLVED"}, {"analogues": [{"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|rare_prime", "shared": {"family": 1.0, "finish": 0.5, "historicalRole": 0.4444444444444444, "mechanic": 0.3333333333333333, "packPosition": null, "pullPosition": null, "visual": 0.8421052631578947}, "similarity": 0.7374561403508773}, {"anchor": "Platinum|Platinum_r1|rare_holo_lv_x", "shared": {"family": 1.0, "finish": 0.5, "historicalRole": 0.4444444444444444, "mechanic": 0.0, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.7088596491228071}, {"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|common", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.5555555555555556, "mechanic": 1.0, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.5771929824561404}], "candidate": "EX|EX|rare_holo_star|Pok\u00e9mon", "case": "older special", "result": "UNRESOLVED"}, {"analogues": [{"anchor": "Diamond and Pearl|Diamond and Pearl_r1|rare_holo", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.7, "mechanic": 1.0, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.5945263157894737}, {"anchor": "Scarlet and Violet|Scarlet and Violet|illustration_rare", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.6666666666666666, "mechanic": 1.0, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.5905263157894737}, {"anchor": "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|rare_holo", "shared": {"family": 0.0, "finish": 1.0, "historicalRole": 0.5, "mechanic": 1.0, "packPosition": null, "pullPosition": null, "visual": 0.8947368421052632}, "similarity": 0.5705263157894738}], "candidate": "Black and White|Black and White|rare_secret|Pok\u00e9mon", "case": "unique unresolved", "result": "UNRESOLVED"}, {"case": "correctly reconstructed holdout", "result": {"actual": 5.012027261014039, "analogueScores": [4.803738618773096, 5.217123525274819, 5.155011983852892, 4.891166310896352], "analogues": ["EX|EX|common", "EX|EX|uncommon", "Diamond and Pearl|Diamond and Pearl_r1|uncommon", "Black and White|Black and White|common"], "era": "Scarlet and Violet", "family": "BASE_PRINT", "nearestSimilarity": 0.9566666666666668, "nodeId": "Scarlet and Violet|Scarlet and Violet|common", "predicted": 5.007689120019026, "premium": false, "sharedFeatures": {"family": 1.0, "finish": 1.0, "historicalRole": 1.0, "mechanic": 0.6666666666666666, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarities": [0.9566666666666668, 0.935, 0.8675, 0.8573333333333334]}}, {"case": "badly predicted holdout", "result": {"actual": 2.490492580557743, "analogueScores": [4.353993694666057, 5.977120162521266, 5.0, 4.681524809551892], "analogues": ["Diamond and Pearl|Diamond and Pearl_r1|rare_holo", "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|rare_holo", "Platinum|Platinum_r1|rare_holo", "EX|EX|rare_holo"], "era": "Black and White", "family": "HOLO_HIT", "nearestSimilarity": 0.8980000000000001, "nodeId": "Black and White|Black and White|rare_holo", "predicted": 4.9267521765242925, "premium": true, "sharedFeatures": {"family": 1.0, "finish": 1.0, "historicalRole": 0.5833333333333334, "mechanic": 0.6, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarities": [0.8980000000000001, 0.8780000000000001, 0.8680000000000001, 0.853]}}]`

60. **failure case study:** `{"actual": 2.490492580557743, "analogueScores": [4.353993694666057, 5.977120162521266, 5.0, 4.681524809551892], "analogues": ["Diamond and Pearl|Diamond and Pearl_r1|rare_holo", "HeartGold and SoulSilver|HeartGold and SoulSilver_r1|rare_holo", "Platinum|Platinum_r1|rare_holo", "EX|EX|rare_holo"], "era": "Black and White", "family": "HOLO_HIT", "nearestSimilarity": 0.8980000000000001, "nodeId": "Black and White|Black and White|rare_holo", "predicted": 4.9267521765242925, "premium": true, "sharedFeatures": {"family": 1.0, "finish": 1.0, "historicalRole": 0.5833333333333334, "mechanic": 0.6, "packPosition": null, "pullPosition": null, "visual": 1.0}, "similarities": [0.8980000000000001, 0.8780000000000001, 0.8680000000000001, 0.853]}`

61. **product-language draft:** `{"direct": "Direct market evidence", "explanation": "This treatment did not have enough standalone observations for a direct estimate. Its score is estimated from empirically validated treatments with similar printing structure, hit frequency, pull position, and collectible role across comparable Pok\u00e9mon eras.", "structural": "Structurally estimated"}`

62. **Collector Appeal status:** `"SEPARATE_INTEGRATION_STUDY_REQUIRED; NO_INTEGRATION_AUTHORIZED"`

63. **Card Detail status:** `"DIRECT_ONLY_CARD_DETAIL_INTEGRATION_STUDY_REMAINS_VALID"`

64. **numeric-fallback final status:** `"NUMERIC_TMP_FALLBACK_EXHAUSTED"`

65. **production pause:** `true`

66. **rows persisted:** `0`

67. **files changed:** `["D:\\EVRCalculator\\backend\\scripts\\build_treatment_market_prestige_v3_round20.py", "docs\\research\\treatment_market_prestige_v3_round20_study.json", "docs\\research\\TREATMENT_MARKET_PRESTIGE_V3_ROUND20_RESULTS.md", "docs\\research\\treatment_market_prestige_v3_round20\\structural_fingerprints.json", "docs\\research\\treatment_market_prestige_v3_round20\\analogue_graph.json", "docs\\research\\treatment_market_prestige_v3_round20\\holdout_validation.json", "docs\\research\\treatment_market_prestige_v3_round20\\target_analogue_availability.json", "docs\\research\\treatment_market_prestige_v3_round20\\structural_inferences.json", "docs\\research\\treatment_market_prestige_v3_round20\\case_studies.json", "docs\\research\\treatment_market_prestige_v3_round20\\manifest.json", "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round20.py"]`

68. **tests executed:** `["Round 20 focused: 4 passed in 7.86s", "Combined V3/Supporter/Trainer regression: 87 passed, 1785 deselected in 113.94s"]`

69. **reproducibility/hash verification:** `{"anchorHash": "9764d4ebe7407c68fa1c9d08ab2fcf2a289c1d2c9a31019a0ad641fe762164c7", "graphHash": "38b9050362fc00ad7f4ff1ceebd323ed90adfb373cd0f00aa59fd7bcfc70f291", "inferenceHash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "targetHash": "1f5d05a58979eae619c174457fabe23aa6916b6ecb42f4faf8130ccb16c531bc", "validationHash": "67faabc24dbd5d696218fc2fbb24dc151199b6baf6b9d77d5d04c4fee934ecdc"}`

70. **limitations:** `["Only direct empirical treatment anchors are ground truth", "authoritative pull evidence is sparse and era-concentrated", "pack-slot architecture is absent from the frozen cohort for most treatments", "structural feature semantics are observable but incomplete", "cross-era market context may not transfer", "no individual card price enters fingerprints or selection"]`

71. **exact recommended next action:** `"If gates fail, stop numeric TMP fallback work and obtain materially new historical, canonical, pull-rate, or pack-architecture evidence; proceed independently with direct-only Card Detail study."`
