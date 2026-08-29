# Treatment Market Prestige V3 — Round 9 Results

Study ID: `treatment-market-prestige-v3-r9-b6e465c2012a6636`

Coverage remains **5,059 / 19,847 (25.5%)**; 14,788 cards are uncovered.

Decision states: `COVERAGE_GAP_MIXED`, `SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT`, `70_PERCENT_COVERAGE_PATH_PLAUSIBLE_BUT_UNPROVEN`.

The 70% gate is not met. Production implementation remains paused and rows persisted remain `0`.

## Required results

1. **Round 9 study ID:** `"treatment-market-prestige-v3-r9-b6e465c2012a6636"`

2. **Priced-card denominator:** `19847`

3. **Currently covered card count:** `5059`

4. **Current coverage percentage:** `0.2548999848843654`

5. **Exact uncovered card count:** `14788`

6. **Primary failure categories:** `["INSUFFICIENT_HISTORY", "INSUFFICIENT_UNIVERSE_SUPPORT", "MISSING_CANONICAL_MAPPING", "MODEL_INSTABILITY", "TAXONOMY_UNMAPPED", "UNSUPPORTED_ERA", "UNSUPPORTED_TREATMENT"]`

7. **Card count per failure category:** `{"INSUFFICIENT_HISTORY": 45, "INSUFFICIENT_UNIVERSE_SUPPORT": 387, "MISSING_CANONICAL_MAPPING": 3561, "MODEL_INSTABILITY": 1717, "TAXONOMY_UNMAPPED": 818, "UNSUPPORTED_ERA": 5486, "UNSUPPORTED_TREATMENT": 2774}`

8. **Percentage per failure category:** `{"INSUFFICIENT_HISTORY": 0.002267345190708923, "INSUFFICIENT_UNIVERSE_SUPPORT": 0.01949916864009674, "MISSING_CANONICAL_MAPPING": 0.17942258275809947, "MODEL_INSTABILITY": 0.08651181538771603, "TAXONOMY_UNMAPPED": 0.04121529702221998, "UNSUPPORTED_ERA": 0.27641457147175896, "UNSUPPORTED_TREATMENT": 0.13976923464503452}`

9. **Overlap/secondary failure categories:** `{"INSUFFICIENT_UNIVERSE_SUPPORT": 4125, "MISSING_CANONICAL_MAPPING": 44}`

10. **Similarity-aware universe-rule audit:** `{"cardsRecoverable": 0, "conclusion": "Round 6 never required unique ordering; failed universes lack two individually eligible treatments.", "equivalentPairs": [{"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "illustration_rare", "scoreDistance": 0.3842801004334193, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "uncommon", "scoreDistance": 0.03913124414660363, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "illustration_rare", "right": "uncommon", "scoreDistance": 0.42341134458002294, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "rare_holo", "scoreDistance": 0.26070604121812213, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "uncommon", "scoreDistance": 0.40833131031858994, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_break", "right": "uncommon", "scoreDistance": 0.2070184840651974, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "uncommon", "scoreDistance": 0.31718201729201123, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "uncommon", "scoreDistance": 0.4448635557361085, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_holo", "right": "rare_rainbow", "scoreDistance": 0.14355591004688328, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_holo_vmax", "right": "rare_ultra", "scoreDistance": 0.16391161856613579, "universeId": "sword_and_shield_r1"}], "existingRule": {"minimum_eligible_treatments": 2, "minimum_sets": 3, "unique_ordering_required": false}, "preregisteredContract": {"pairwiseOrderingProbabilityAloneIsDispositive": false, "requirements": ["both treatment magnitude estimates pass every individual gate", "absolute score distance <= margin", "propagated score intervals may overlap", "prediction widths pass heterogeneity gates", "temporal status is MARKET_MOVEMENT"], "scoreDistanceMargin": 0.5}, "ruleAudit": "SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT"}`

11. **Treatments currently stable but practically equivalent:** `[{"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "illustration_rare", "scoreDistance": 0.3842801004334193, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "uncommon", "scoreDistance": 0.03913124414660363, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "illustration_rare", "right": "uncommon", "scoreDistance": 0.42341134458002294, "universeId": "Scarlet and Violet"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "rare_holo", "scoreDistance": 0.26070604121812213, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "uncommon", "scoreDistance": 0.40833131031858994, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_break", "right": "uncommon", "scoreDistance": 0.2070184840651974, "universeId": "XY"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "common", "right": "uncommon", "scoreDistance": 0.31718201729201123, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare", "right": "uncommon", "scoreDistance": 0.4448635557361085, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_holo", "right": "rare_rainbow", "scoreDistance": 0.14355591004688328, "universeId": "sun_and_moon_r1"}, {"classification": "PRACTICALLY_EQUIVALENT_PRESTIGE", "left": "rare_holo_vmax", "right": "rare_ultra", "scoreDistance": 0.16391161856613579, "universeId": "sword_and_shield_r1"}]`

12. **Cards recoverable through similarity-aware semantics:** `0`

13. **Mega gap decomposition:** `{"cards": 992, "coveredCards": 0, "era": "Mega Evolution", "primaryBlockers": {"INSUFFICIENT_HISTORY": 45, "INSUFFICIENT_UNIVERSE_SUPPORT": 88, "MISSING_CANONICAL_MAPPING": 204, "MODEL_INSTABILITY": 599, "UNSUPPORTED_TREATMENT": 56}, "publicationStatus": "INSUFFICIENT_ERA_SUPPORT", "treatmentEvidence": [{"cardCount": 288, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 4.997539801214917, "scoreInterval": null, "setCount": 6, "speciesCount": 250, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "common"}, {"cardCount": 88, "evidenceStatus": "AVAILABLE", "finalAvailabilityStatus": "INSUFFICIENT_ERA_SUPPORT", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 2.86662482489956, "scoreInterval": null, "setCount": 6, "speciesCount": 83, "temporalStatus": "MARKET_MOVEMENT", "treatmentKey": "double_rare"}, {"cardCount": 101, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 7.331355374980519, "scoreInterval": null, "setCount": 6, "speciesCount": 100, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "illustration_rare"}, {"cardCount": 72, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 5.493771971010635, "scoreInterval": null, "setCount": 6, "speciesCount": 68, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "rare"}, {"cardCount": 45, "evidenceStatus": "INSUFFICIENT_HISTORY", "finalAvailabilityStatus": "INSUFFICIENT_HISTORY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 3.7944007503093737, "scoreInterval": null, "setCount": 6, "speciesCount": 45, "temporalStatus": "INSUFFICIENT_HISTORY", "treatmentKey": "ultra_rare"}, {"cardCount": 138, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 4.989059358763905, "scoreInterval": null, "setCount": 6, "speciesCount": 122, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "uncommon"}], "uncoveredCards": 992, "universeId": "Mega Evolution"}`

14. **Mega recoverable coverage:** `{"opportunity": 992, "validated": 0}`

15. **SWSH regime 2 gap:** `{"cards": 775, "coveredCards": 0, "era": "Sword and Shield", "primaryBlockers": {"MISSING_CANONICAL_MAPPING": 146, "MODEL_INSTABILITY": 90, "UNSUPPORTED_TREATMENT": 539}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [{"cardCount": 54, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 9.0, "scoreInterval": null, "setCount": 4, "speciesCount": 52, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "rare_holo_v"}, {"cardCount": 36, "evidenceStatus": "MODEL_INSTABILITY", "finalAvailabilityStatus": "MODEL_INSTABILITY", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 9.0, "scoreInterval": null, "setCount": 4, "speciesCount": 34, "temporalStatus": "MODEL_INSTABILITY", "treatmentKey": "rare_holo_vmax"}], "uncoveredCards": 775, "universeId": "sword_and_shield_r2"}`

16. **SWSH regime 3 gap:** `{"cards": 583, "coveredCards": 0, "era": "Sword and Shield", "primaryBlockers": {"INSUFFICIENT_UNIVERSE_SUPPORT": 58, "MISSING_CANONICAL_MAPPING": 92, "UNSUPPORTED_TREATMENT": 433}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [{"cardCount": 58, "evidenceStatus": "AVAILABLE", "finalAvailabilityStatus": "INSUFFICIENT_REGIME_SUPPORT", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 2.504484285227715, "scoreInterval": null, "setCount": 5, "speciesCount": 48, "temporalStatus": "MARKET_MOVEMENT", "treatmentKey": "rare_holo_v"}], "uncoveredCards": 583, "universeId": "sword_and_shield_r3"}`

17. **SWSH regime 4 gap:** `{"cards": 526, "coveredCards": 0, "era": "Sword and Shield", "primaryBlockers": {"MISSING_CANONICAL_MAPPING": 108, "UNSUPPORTED_TREATMENT": 418}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [], "uncoveredCards": 526, "universeId": "sword_and_shield_r4"}`

18. **SWSH regime 5 gap:** `{"cards": 506, "coveredCards": 0, "era": "Sword and Shield", "primaryBlockers": {"INSUFFICIENT_UNIVERSE_SUPPORT": 55, "MISSING_CANONICAL_MAPPING": 98, "UNSUPPORTED_TREATMENT": 353}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [{"cardCount": 55, "evidenceStatus": "AVAILABLE", "finalAvailabilityStatus": "INSUFFICIENT_REGIME_SUPPORT", "heterogeneityStatus": "WITHIN_GATE", "researchScore": 3.71816114756977, "scoreInterval": null, "setCount": 5, "speciesCount": 50, "temporalStatus": "MARKET_MOVEMENT", "treatmentKey": "rare_holo_v"}], "uncoveredCards": 506, "universeId": "sword_and_shield_r5"}`

19. **SWSH total recoverable coverage:** `{"opportunity": 2390, "validated": 0}`

20. **Sun & Moon regime 2 gap:** `{"cards": 510, "coveredCards": 0, "era": "Sun and Moon", "primaryBlockers": {"MISSING_CANONICAL_MAPPING": 124, "UNSUPPORTED_TREATMENT": 386}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [], "uncoveredCards": 510, "universeId": "sun_and_moon_r2"}`

21. **Sun & Moon regime 3 gap:** `{"cards": 434, "coveredCards": 0, "era": "Sun and Moon", "primaryBlockers": {"MISSING_CANONICAL_MAPPING": 102, "UNSUPPORTED_TREATMENT": 332}, "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT", "treatmentEvidence": [], "uncoveredCards": 434, "universeId": "sun_and_moon_r3"}`

22. **Sun & Moon total recoverable coverage:** `{"opportunity": 944, "validated": 0}`

23. **Every older-era support audit:** `{"Base/WOTC": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Base/WOTC", "mappedTreatmentCards": 429, "pricedCanonicalCards": 441, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 5, "species": 150, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "rare_secret", "uncommon"]}, "Black and White": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Black and White", "mappedTreatmentCards": 1444, "pricedCanonicalCards": 1447, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 14, "species": 487, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "promo", "rare", "rare_ace", "rare_holo", "rare_holo_ex", "rare_secret", "rare_ultra", "uncommon"]}, "Diamond and Pearl": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Diamond and Pearl", "mappedTreatmentCards": 844, "pricedCanonicalCards": 844, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 7, "species": 490, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "rare_holo_lv_x", "rare_secret", "uncommon"]}, "E-Card": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "E-Card", "mappedTreatmentCards": 513, "pricedCanonicalCards": 519, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 3, "species": 246, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "holo_rare", "rare", "rare_holo", "rare_secret", "uncommon"]}, "EX": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "EX", "mappedTreatmentCards": 1701, "pricedCanonicalCards": 1701, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 16, "species": 384, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "rare_holo_ex", "rare_holo_star", "rare_secret", "uncommon"]}, "Gym": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Gym", "mappedTreatmentCards": 253, "pricedCanonicalCards": 265, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 2, "species": 124, "supportStatus": "INSUFFICIENT_DATA", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "ultra_rare", "uncommon"]}, "HeartGold and SoulSilver": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "HeartGold and SoulSilver", "mappedTreatmentCards": 549, "pricedCanonicalCards": 549, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 6, "species": 306, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "legend", "promo", "rare", "rare_holo", "rare_prime", "rare_secret", "uncommon"]}, "NP": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "NP", "mappedTreatmentCards": 74, "pricedCanonicalCards": 74, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 1, "species": 21, "supportStatus": "INSUFFICIENT_DATA", "temporalCheckpointDepth": 0, "treatments": ["promo"]}, "Neo": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Neo", "mappedTreatmentCards": 358, "pricedCanonicalCards": 364, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 4, "species": 175, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "rare_shining", "uncommon"]}, "Other": {"dataRequirement": "NEW_TAXONOMY_RESEARCH_REQUIRED", "earliestUsableDate": null, "era": "Other", "mappedTreatmentCards": 111, "pricedCanonicalCards": 271, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 13, "species": 191, "supportStatus": "TAXONOMY_REPAIR_REQUIRED", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "uncommon"]}, "POP": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "POP", "mappedTreatmentCards": 153, "pricedCanonicalCards": 153, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 9, "species": 107, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "uncommon"]}, "Platinum": {"dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "earliestUsableDate": null, "era": "Platinum", "mappedTreatmentCards": 517, "pricedCanonicalCards": 517, "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "sets": 4, "species": 309, "supportStatus": "INSUFFICIENT_HISTORY", "temporalCheckpointDepth": 0, "treatments": ["common", "rare", "rare_holo", "rare_holo_lv_x", "rare_secret", "uncommon"]}}`

24. **Older-era taxonomy gaps:** `{"Base/WOTC": "INSUFFICIENT_HISTORY", "Black and White": "INSUFFICIENT_HISTORY", "Diamond and Pearl": "INSUFFICIENT_HISTORY", "E-Card": "INSUFFICIENT_HISTORY", "EX": "INSUFFICIENT_HISTORY", "Gym": "INSUFFICIENT_DATA", "HeartGold and SoulSilver": "INSUFFICIENT_HISTORY", "NP": "INSUFFICIENT_DATA", "Neo": "INSUFFICIENT_HISTORY", "Other": "TAXONOMY_REPAIR_REQUIRED", "POP": "INSUFFICIENT_HISTORY", "Platinum": "INSUFFICIENT_HISTORY"}`

25. **Older-era temporal gaps:** `{"Base/WOTC": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Black and White": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Diamond and Pearl": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "E-Card": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "EX": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Gym": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "HeartGold and SoulSilver": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "NP": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Neo": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Other": {"checkpointDepth": 0, "requirement": "NEW_TAXONOMY_RESEARCH_REQUIRED"}, "POP": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}, "Platinum": {"checkpointDepth": 0, "requirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED"}}`

26. **Era-vs-regime recommendation per older era:** `{"Base/WOTC": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Black and White": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Diamond and Pearl": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "E-Card": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "EX": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Gym": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "HeartGold and SoulSilver": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "NP": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Neo": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Other": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "POP": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION", "Platinum": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION"}`

27. **Internal vs external data requirements:** `{"INSUFFICIENT_HISTORY": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "INSUFFICIENT_UNIVERSE_SUPPORT": "INTERNAL_PIPELINE_REPAIR_REQUIRED", "MISSING_CANONICAL_MAPPING": "NEW_CANONICAL_MAPPING_REQUIRED", "MODEL_INSTABILITY": "INTERNAL_DATA_ALREADY_EXISTS", "TAXONOMY_UNMAPPED": "NEW_TAXONOMY_RESEARCH_REQUIRED", "UNSUPPORTED_ERA": "EXTERNAL_HISTORICAL_DATA_REQUIRED", "UNSUPPORTED_TREATMENT": "NEW_TAXONOMY_RESEARCH_REQUIRED"}`

28. **Coverage opportunity table:** `[{"currentlyUncoveredCards": 5486, "externalDataRequired": true, "gainIsValidated": false, "implementationComplexity": "high", "percentagePointGain": 27.641457147175895, "primaryBlocker": "UNSUPPORTED_ERA", "project": "Resolve UNSUPPORTED_ERA", "scientificRisk": "high", "theoreticalCumulativeCoverage": 0.5313145563561243, "workType": "taxonomy+data+research"}, {"currentlyUncoveredCards": 3561, "externalDataRequired": false, "gainIsValidated": false, "implementationComplexity": "medium", "percentagePointGain": 17.942258275809944, "primaryBlocker": "MISSING_CANONICAL_MAPPING", "project": "Resolve MISSING_CANONICAL_MAPPING", "scientificRisk": "medium", "theoreticalCumulativeCoverage": 0.7107371391142238, "workType": "canonical mapping"}, {"currentlyUncoveredCards": 2774, "externalDataRequired": false, "gainIsValidated": false, "implementationComplexity": "medium", "percentagePointGain": 13.976923464503452, "primaryBlocker": "UNSUPPORTED_TREATMENT", "project": "Resolve UNSUPPORTED_TREATMENT", "scientificRisk": "medium", "theoreticalCumulativeCoverage": 0.8505063737592583, "workType": "taxonomy+research"}, {"currentlyUncoveredCards": 1717, "externalDataRequired": false, "gainIsValidated": false, "implementationComplexity": "high", "percentagePointGain": 8.651181538771603, "primaryBlocker": "MODEL_INSTABILITY", "project": "Resolve MODEL_INSTABILITY", "scientificRisk": "high", "theoreticalCumulativeCoverage": 0.9370181891469743, "workType": "research"}, {"currentlyUncoveredCards": 818, "externalDataRequired": false, "gainIsValidated": false, "implementationComplexity": "medium", "percentagePointGain": 4.1215297022219985, "primaryBlocker": "TAXONOMY_UNMAPPED", "project": "Resolve TAXONOMY_UNMAPPED", "scientificRisk": "medium", "theoreticalCumulativeCoverage": 0.9782334861691944, "workType": "taxonomy"}, {"currentlyUncoveredCards": 387, "externalDataRequired": false, "gainIsValidated": false, "implementationComplexity": "high", "percentagePointGain": 1.949916864009674, "primaryBlocker": "INSUFFICIENT_UNIVERSE_SUPPORT", "project": "Resolve INSUFFICIENT_UNIVERSE_SUPPORT", "scientificRisk": "high", "theoreticalCumulativeCoverage": 0.9977326548092911, "workType": "research"}, {"currentlyUncoveredCards": 45, "externalDataRequired": true, "gainIsValidated": false, "implementationComplexity": "medium", "percentagePointGain": 0.22673451907089232, "primaryBlocker": "INSUFFICIENT_HISTORY", "project": "Resolve INSUFFICIENT_HISTORY", "scientificRisk": "medium", "theoreticalCumulativeCoverage": 1.0, "workType": "data"}]`

29. **Internal-only maximum coverage:** `{"maximumPlausible": 5059, "note": "No failed project has yet passed the frozen evidence gates.", "validatedFloor": 5059}`

30. **Historical-backfill coverage:** `{"maximumPlausible": 5104, "unproven": true, "validatedFloor": 5059}`

31. **External-history coverage:** `{"maximumPlausible": 15468, "unproven": true, "validatedFloor": 5059}`

32. **Full-research potential coverage:** `{"theoreticalCeiling": 19847, "unproven": true, "validatedFloor": 5059}`

33. **Minimum path to 50%:** `{"minimumValidatedProjects": null, "reason": "No unresolved project has passed the unchanged evidence gates.", "status": "PLAUSIBLE_BUT_UNPROVEN"}`

34. **Minimum path to 60%:** `{"minimumValidatedProjects": null, "status": "PLAUSIBLE_BUT_UNPROVEN"}`

35. **Minimum path to 70%:** `{"minimumValidatedProjects": null, "status": "PLAUSIBLE_BUT_UNPROVEN"}`

36. **Path to 80% if credible:** `{"minimumValidatedProjects": null, "status": "PLAUSIBLE_BUT_UNPROVEN"}`

37. **Coverage diagnosis status:** `"COVERAGE_GAP_MIXED"`

38. **Similarity-rule status:** `"SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT"`

39. **70% path status:** `"70_PERCENT_COVERAGE_PATH_PLAUSIBLE_BUT_UNPROVEN"`

40. **Whether production implementation should remain paused:** `true`

41. **Rows persisted:** `0`

42. **Production behavior:** `"Unchanged; research artifacts only. No migration applied, candidate approved, reader activated, UI/frontend/RIP/V1/V2/ranking behavior changed."`

43. **Files changed:** `["docs\\research\\treatment_market_prestige_v3_round9_coverage\\card_coverage.json", "docs\\research\\treatment_market_prestige_v3_round9_coverage\\manifest.json", "docs\\research\\treatment_market_prestige_v3_round9_study.json", "docs\\research\\TREATMENT_MARKET_PRESTIGE_V3_ROUND9_RESULTS.md", "backend/scripts/build_treatment_market_prestige_v3_round9.py", "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round9.py"]`

44. **Tests executed:** `["Round 9 exhaustive card accounting", "similarity semantics", "70% fail-closed product gate"]`

45. **Remaining limitations:** `["Older eras have no frozen four-checkpoint temporal evidence", "opportunity counts are not eligibility claims", "no new external data was introduced"]`

46. **Exact recommended next research/data tasks in priority order:** `["Backfill and validate existing failed modern regimes by coverage gain", "Research older-era structural ontologies", "Acquire and freeze authoritative older-era history", "Rerun the unchanged individual evidence gates"]`

## Machine-readable complete report

```json
{
  "blockerDataRequirements": {
    "INSUFFICIENT_HISTORY": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
    "INSUFFICIENT_UNIVERSE_SUPPORT": "INTERNAL_PIPELINE_REPAIR_REQUIRED",
    "MISSING_CANONICAL_MAPPING": "NEW_CANONICAL_MAPPING_REQUIRED",
    "MODEL_INSTABILITY": "INTERNAL_DATA_ALREADY_EXISTS",
    "TAXONOMY_UNMAPPED": "NEW_TAXONOMY_RESEARCH_REQUIRED",
    "UNSUPPORTED_ERA": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
    "UNSUPPORTED_TREATMENT": "NEW_TAXONOMY_RESEARCH_REQUIRED"
  },
  "built_at": "2026-08-29T21:33:00.122907+00:00",
  "cardResultsFile": "docs\\research\\treatment_market_prestige_v3_round9_coverage\\card_coverage.json",
  "catalogProductCoverageTarget": 0.7,
  "coverageDiagnosis": "COVERAGE_GAP_MIXED",
  "coverageOpportunityTable": [
    {
      "currentlyUncoveredCards": 5486,
      "externalDataRequired": true,
      "gainIsValidated": false,
      "implementationComplexity": "high",
      "percentagePointGain": 27.641457147175895,
      "primaryBlocker": "UNSUPPORTED_ERA",
      "project": "Resolve UNSUPPORTED_ERA",
      "scientificRisk": "high",
      "theoreticalCumulativeCoverage": 0.5313145563561243,
      "workType": "taxonomy+data+research"
    },
    {
      "currentlyUncoveredCards": 3561,
      "externalDataRequired": false,
      "gainIsValidated": false,
      "implementationComplexity": "medium",
      "percentagePointGain": 17.942258275809944,
      "primaryBlocker": "MISSING_CANONICAL_MAPPING",
      "project": "Resolve MISSING_CANONICAL_MAPPING",
      "scientificRisk": "medium",
      "theoreticalCumulativeCoverage": 0.7107371391142238,
      "workType": "canonical mapping"
    },
    {
      "currentlyUncoveredCards": 2774,
      "externalDataRequired": false,
      "gainIsValidated": false,
      "implementationComplexity": "medium",
      "percentagePointGain": 13.976923464503452,
      "primaryBlocker": "UNSUPPORTED_TREATMENT",
      "project": "Resolve UNSUPPORTED_TREATMENT",
      "scientificRisk": "medium",
      "theoreticalCumulativeCoverage": 0.8505063737592583,
      "workType": "taxonomy+research"
    },
    {
      "currentlyUncoveredCards": 1717,
      "externalDataRequired": false,
      "gainIsValidated": false,
      "implementationComplexity": "high",
      "percentagePointGain": 8.651181538771603,
      "primaryBlocker": "MODEL_INSTABILITY",
      "project": "Resolve MODEL_INSTABILITY",
      "scientificRisk": "high",
      "theoreticalCumulativeCoverage": 0.9370181891469743,
      "workType": "research"
    },
    {
      "currentlyUncoveredCards": 818,
      "externalDataRequired": false,
      "gainIsValidated": false,
      "implementationComplexity": "medium",
      "percentagePointGain": 4.1215297022219985,
      "primaryBlocker": "TAXONOMY_UNMAPPED",
      "project": "Resolve TAXONOMY_UNMAPPED",
      "scientificRisk": "medium",
      "theoreticalCumulativeCoverage": 0.9782334861691944,
      "workType": "taxonomy"
    },
    {
      "currentlyUncoveredCards": 387,
      "externalDataRequired": false,
      "gainIsValidated": false,
      "implementationComplexity": "high",
      "percentagePointGain": 1.949916864009674,
      "primaryBlocker": "INSUFFICIENT_UNIVERSE_SUPPORT",
      "project": "Resolve INSUFFICIENT_UNIVERSE_SUPPORT",
      "scientificRisk": "high",
      "theoreticalCumulativeCoverage": 0.9977326548092911,
      "workType": "research"
    },
    {
      "currentlyUncoveredCards": 45,
      "externalDataRequired": true,
      "gainIsValidated": false,
      "implementationComplexity": "medium",
      "percentagePointGain": 0.22673451907089232,
      "primaryBlocker": "INSUFFICIENT_HISTORY",
      "project": "Resolve INSUFFICIENT_HISTORY",
      "scientificRisk": "medium",
      "theoreticalCumulativeCoverage": 1.0,
      "workType": "data"
    }
  ],
  "currentAuthoritativeDenominator": 19847,
  "currentCoverage": 0.2548999848843654,
  "currentlyCoveredCards": 5059,
  "filesChanged": [
    "docs\\research\\treatment_market_prestige_v3_round9_coverage\\card_coverage.json",
    "docs\\research\\treatment_market_prestige_v3_round9_coverage\\manifest.json",
    "docs\\research\\treatment_market_prestige_v3_round9_study.json",
    "docs\\research\\TREATMENT_MARKET_PRESTIGE_V3_ROUND9_RESULTS.md",
    "backend/scripts/build_treatment_market_prestige_v3_round9.py",
    "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round9.py"
  ],
  "frozenRound8Denominator": 19847,
  "olderEraAudit": [
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Base/WOTC",
      "mappedTreatmentCards": 429,
      "pricedCanonicalCards": 441,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 5,
      "species": 150,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "rare_secret",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Black and White",
      "mappedTreatmentCards": 1444,
      "pricedCanonicalCards": 1447,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 14,
      "species": 487,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "promo",
        "rare",
        "rare_ace",
        "rare_holo",
        "rare_holo_ex",
        "rare_secret",
        "rare_ultra",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Diamond and Pearl",
      "mappedTreatmentCards": 844,
      "pricedCanonicalCards": 844,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 7,
      "species": 490,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "rare_holo_lv_x",
        "rare_secret",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "E-Card",
      "mappedTreatmentCards": 513,
      "pricedCanonicalCards": 519,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 3,
      "species": 246,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "holo_rare",
        "rare",
        "rare_holo",
        "rare_secret",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "EX",
      "mappedTreatmentCards": 1701,
      "pricedCanonicalCards": 1701,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 16,
      "species": 384,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "rare_holo_ex",
        "rare_holo_star",
        "rare_secret",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Gym",
      "mappedTreatmentCards": 253,
      "pricedCanonicalCards": 265,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 2,
      "species": 124,
      "supportStatus": "INSUFFICIENT_DATA",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "ultra_rare",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "HeartGold and SoulSilver",
      "mappedTreatmentCards": 549,
      "pricedCanonicalCards": 549,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 6,
      "species": 306,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "legend",
        "promo",
        "rare",
        "rare_holo",
        "rare_prime",
        "rare_secret",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "NP",
      "mappedTreatmentCards": 74,
      "pricedCanonicalCards": 74,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 1,
      "species": 21,
      "supportStatus": "INSUFFICIENT_DATA",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "promo"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Neo",
      "mappedTreatmentCards": 358,
      "pricedCanonicalCards": 364,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 4,
      "species": 175,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "rare_shining",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "NEW_TAXONOMY_RESEARCH_REQUIRED",
      "earliestUsableDate": null,
      "era": "Other",
      "mappedTreatmentCards": 111,
      "pricedCanonicalCards": 271,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 13,
      "species": 191,
      "supportStatus": "TAXONOMY_REPAIR_REQUIRED",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "POP",
      "mappedTreatmentCards": 153,
      "pricedCanonicalCards": 153,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 9,
      "species": 107,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "uncommon"
      ]
    },
    {
      "dataRequirement": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
      "earliestUsableDate": null,
      "era": "Platinum",
      "mappedTreatmentCards": 517,
      "pricedCanonicalCards": 517,
      "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
      "sets": 4,
      "species": 309,
      "supportStatus": "INSUFFICIENT_HISTORY",
      "temporalCheckpointDepth": 0,
      "treatments": [
        "common",
        "rare",
        "rare_holo",
        "rare_holo_lv_x",
        "rare_secret",
        "uncommon"
      ]
    }
  ],
  "preservedImplementationScaffolding": [
    "supabase/migrations/20260830020000_create_treatment_market_prestige_v3_publication.sql",
    "backend/db/services/treatment_market_prestige_v3_service.py",
    "backend/scripts/build_treatment_market_prestige_v3_candidate.py",
    "backend/scripts/approve_treatment_market_prestige_v3_candidate.py",
    "backend/scripts/verify_treatment_market_prestige_v3_production.py"
  ],
  "primaryFailureCategories": {
    "INSUFFICIENT_HISTORY": 45,
    "INSUFFICIENT_UNIVERSE_SUPPORT": 387,
    "MISSING_CANONICAL_MAPPING": 3561,
    "MODEL_INSTABILITY": 1717,
    "TAXONOMY_UNMAPPED": 818,
    "UNSUPPORTED_ERA": 5486,
    "UNSUPPORTED_TREATMENT": 2774
  },
  "primaryFailurePercentages": {
    "INSUFFICIENT_HISTORY": 0.002267345190708923,
    "INSUFFICIENT_UNIVERSE_SUPPORT": 0.01949916864009674,
    "MISSING_CANONICAL_MAPPING": 0.17942258275809947,
    "MODEL_INSTABILITY": 0.08651181538771603,
    "TAXONOMY_UNMAPPED": 0.04121529702221998,
    "UNSUPPORTED_ERA": 0.27641457147175896,
    "UNSUPPORTED_TREATMENT": 0.13976923464503452
  },
  "productStatus": "CATALOG_COVERAGE_BELOW_PRODUCT_THRESHOLD",
  "productionBehavior": "Unchanged; research artifacts only. No migration applied, candidate approved, reader activated, UI/frontend/RIP/V1/V2/ranking behavior changed.",
  "productionImplementationPaused": true,
  "recommendedTasks": [
    "Backfill and validate existing failed modern regimes by coverage gain",
    "Research older-era structural ontologies",
    "Acquire and freeze authoritative older-era history",
    "Rerun the unchanged individual evidence gates"
  ],
  "remainingLimitations": [
    "Older eras have no frozen four-checkpoint temporal evidence",
    "opportunity counts are not eligibility claims",
    "no new external data was introduced"
  ],
  "rowsPersisted": 0,
  "scenarios": {
    "fullOlderEraResearch": {
      "theoreticalCeiling": 19847,
      "unproven": true,
      "validatedFloor": 5059
    },
    "internalHistoricalBackfill": {
      "maximumPlausible": 5104,
      "unproven": true,
      "validatedFloor": 5059
    },
    "internalOnly": {
      "maximumPlausible": 5059,
      "note": "No failed project has yet passed the frozen evidence gates.",
      "validatedFloor": 5059
    },
    "verifiedExternalHistory": {
      "maximumPlausible": 15468,
      "unproven": true,
      "validatedFloor": 5059
    }
  },
  "secondaryFailureCategories": {
    "INSUFFICIENT_UNIVERSE_SUPPORT": 4125,
    "MISSING_CANONICAL_MAPPING": 44
  },
  "seventyPercentPathStatus": "70_PERCENT_COVERAGE_PATH_PLAUSIBLE_BUT_UNPROVEN",
  "similarityAudit": {
    "cardsRecoverable": 0,
    "conclusion": "Round 6 never required unique ordering; failed universes lack two individually eligible treatments.",
    "equivalentPairs": [
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "common",
        "right": "illustration_rare",
        "scoreDistance": 0.3842801004334193,
        "universeId": "Scarlet and Violet"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "common",
        "right": "uncommon",
        "scoreDistance": 0.03913124414660363,
        "universeId": "Scarlet and Violet"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "illustration_rare",
        "right": "uncommon",
        "scoreDistance": 0.42341134458002294,
        "universeId": "Scarlet and Violet"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare",
        "right": "rare_holo",
        "scoreDistance": 0.26070604121812213,
        "universeId": "XY"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare",
        "right": "uncommon",
        "scoreDistance": 0.40833131031858994,
        "universeId": "XY"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare_break",
        "right": "uncommon",
        "scoreDistance": 0.2070184840651974,
        "universeId": "XY"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "common",
        "right": "uncommon",
        "scoreDistance": 0.31718201729201123,
        "universeId": "sun_and_moon_r1"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare",
        "right": "uncommon",
        "scoreDistance": 0.4448635557361085,
        "universeId": "sun_and_moon_r1"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare_holo",
        "right": "rare_rainbow",
        "scoreDistance": 0.14355591004688328,
        "universeId": "sun_and_moon_r1"
      },
      {
        "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE",
        "left": "rare_holo_vmax",
        "right": "rare_ultra",
        "scoreDistance": 0.16391161856613579,
        "universeId": "sword_and_shield_r1"
      }
    ],
    "existingRule": {
      "minimum_eligible_treatments": 2,
      "minimum_sets": 3,
      "unique_ordering_required": false
    },
    "preregisteredContract": {
      "pairwiseOrderingProbabilityAloneIsDispositive": false,
      "requirements": [
        "both treatment magnitude estimates pass every individual gate",
        "absolute score distance <= margin",
        "propagated score intervals may overlap",
        "prediction widths pass heterogeneity gates",
        "temporal status is MARKET_MOVEMENT"
      ],
      "scoreDistanceMargin": 0.5
    },
    "ruleAudit": "SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT"
  },
  "similarityRuleStatus": "SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT",
  "study_id": "treatment-market-prestige-v3-r9-b6e465c2012a6636",
  "testsExecuted": [
    "Round 9 exhaustive card accounting",
    "similarity semantics",
    "70% fail-closed product gate"
  ],
  "thresholdPaths": {
    "50Percent": {
      "minimumValidatedProjects": null,
      "reason": "No unresolved project has passed the unchanged evidence gates.",
      "status": "PLAUSIBLE_BUT_UNPROVEN"
    },
    "60Percent": {
      "minimumValidatedProjects": null,
      "status": "PLAUSIBLE_BUT_UNPROVEN"
    },
    "70Percent": {
      "minimumValidatedProjects": null,
      "status": "PLAUSIBLE_BUT_UNPROVEN"
    },
    "80Percent": {
      "minimumValidatedProjects": null,
      "status": "PLAUSIBLE_BUT_UNPROVEN"
    }
  },
  "uncoveredCards": 14788,
  "universeGapDecomposition": [
    {
      "cards": 987,
      "coveredCards": 163,
      "era": "Sword and Shield",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 185,
        "MODEL_INSTABILITY": 595,
        "UNSUPPORTED_TREATMENT": 44
      },
      "publicationStatus": "AVAILABLE",
      "treatmentEvidence": [
        {
          "cardCount": 243,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.601663321005628,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 177,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "common"
        },
        {
          "cardCount": 137,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.73728048601537,
          "scoreInterval": null,
          "setCount": 5,
          "speciesCount": 117,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "rare"
        },
        {
          "cardCount": 83,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.8040640504747905,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 71,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "rare_holo"
        },
        {
          "cardCount": 77,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.9939959967887146,
          "scoreInterval": [
            2.967892530119726,
            3.0233686338882935
          ],
          "setCount": 6,
          "speciesCount": 70,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_v"
        },
        {
          "cardCount": 33,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.5928664719919174,
          "scoreInterval": [
            3.5019873598451268,
            3.7250434792642086
          ],
          "setCount": 6,
          "speciesCount": 31,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_vmax"
        },
        {
          "cardCount": 53,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.7567780905580532,
          "scoreInterval": [
            3.7007949675330702,
            3.8035836442018445
          ],
          "setCount": 6,
          "speciesCount": 53,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_ultra"
        },
        {
          "cardCount": 132,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.364000818799961,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 116,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "uncommon"
        }
      ],
      "uncoveredCards": 824,
      "universeId": "sword_and_shield_r1"
    },
    {
      "cards": 775,
      "coveredCards": 0,
      "era": "Sword and Shield",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 146,
        "MODEL_INSTABILITY": 90,
        "UNSUPPORTED_TREATMENT": 539
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [
        {
          "cardCount": 54,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 9.0,
          "scoreInterval": null,
          "setCount": 4,
          "speciesCount": 52,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "rare_holo_v"
        },
        {
          "cardCount": 36,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 9.0,
          "scoreInterval": null,
          "setCount": 4,
          "speciesCount": 34,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "rare_holo_vmax"
        }
      ],
      "uncoveredCards": 775,
      "universeId": "sword_and_shield_r2"
    },
    {
      "cards": 583,
      "coveredCards": 0,
      "era": "Sword and Shield",
      "primaryBlockers": {
        "INSUFFICIENT_UNIVERSE_SUPPORT": 58,
        "MISSING_CANONICAL_MAPPING": 92,
        "UNSUPPORTED_TREATMENT": 433
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [
        {
          "cardCount": 58,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "INSUFFICIENT_REGIME_SUPPORT",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.504484285227715,
          "scoreInterval": null,
          "setCount": 5,
          "speciesCount": 48,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_v"
        }
      ],
      "uncoveredCards": 583,
      "universeId": "sword_and_shield_r3"
    },
    {
      "cards": 526,
      "coveredCards": 0,
      "era": "Sword and Shield",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 108,
        "UNSUPPORTED_TREATMENT": 418
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [],
      "uncoveredCards": 526,
      "universeId": "sword_and_shield_r4"
    },
    {
      "cards": 506,
      "coveredCards": 0,
      "era": "Sword and Shield",
      "primaryBlockers": {
        "INSUFFICIENT_UNIVERSE_SUPPORT": 55,
        "MISSING_CANONICAL_MAPPING": 98,
        "UNSUPPORTED_TREATMENT": 353
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [
        {
          "cardCount": 55,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "INSUFFICIENT_REGIME_SUPPORT",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.71816114756977,
          "scoreInterval": null,
          "setCount": 5,
          "speciesCount": 50,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_v"
        }
      ],
      "uncoveredCards": 506,
      "universeId": "sword_and_shield_r5"
    },
    {
      "cards": 2025,
      "coveredCards": 1341,
      "era": "Sun and Moon",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 477,
        "TAXONOMY_UNMAPPED": 181,
        "UNSUPPORTED_TREATMENT": 26
      },
      "publicationStatus": "AVAILABLE",
      "treatmentEvidence": [
        {
          "cardCount": 422,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.036824169355605,
          "scoreInterval": [
            5.012526038124808,
            5.058946683986483
          ],
          "setCount": 11,
          "speciesCount": 247,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "common"
        },
        {
          "cardCount": 220,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.798869742383725,
          "scoreInterval": [
            5.7679419409461685,
            5.841747878669194
          ],
          "setCount": 9,
          "speciesCount": 166,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare"
        },
        {
          "cardCount": 155,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.9303640102475708,
          "scoreInterval": [
            3.810526419111599,
            4.043164160770173
          ],
          "setCount": 11,
          "speciesCount": 136,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo"
        },
        {
          "cardCount": 98,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.886186492127025,
          "scoreInterval": [
            2.85277674105245,
            2.927241792696437
          ],
          "setCount": 11,
          "speciesCount": 88,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_gx"
        },
        {
          "cardCount": 96,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.073919920294454,
          "scoreInterval": [
            3.9779999031083,
            4.1450142930836265
          ],
          "setCount": 11,
          "speciesCount": 88,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_rainbow"
        },
        {
          "cardCount": 91,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.4253173082258934,
          "scoreInterval": [
            3.382522523145712,
            3.4838563002951863
          ],
          "setCount": 11,
          "speciesCount": 84,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_ultra"
        },
        {
          "cardCount": 259,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.3540061866476165,
          "scoreInterval": [
            5.3121922929345375,
            5.387412298663397
          ],
          "setCount": 11,
          "speciesCount": 206,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "uncommon"
        }
      ],
      "uncoveredCards": 684,
      "universeId": "sun_and_moon_r1"
    },
    {
      "cards": 510,
      "coveredCards": 0,
      "era": "Sun and Moon",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 124,
        "UNSUPPORTED_TREATMENT": 386
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [],
      "uncoveredCards": 510,
      "universeId": "sun_and_moon_r2"
    },
    {
      "cards": 434,
      "coveredCards": 0,
      "era": "Sun and Moon",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 102,
        "UNSUPPORTED_TREATMENT": 332
      },
      "publicationStatus": "INSUFFICIENT_REGIME_SUPPORT",
      "treatmentEvidence": [],
      "uncoveredCards": 434,
      "universeId": "sun_and_moon_r3"
    },
    {
      "cards": 1930,
      "coveredCards": 897,
      "era": "XY",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 367,
        "MODEL_INSTABILITY": 433,
        "TAXONOMY_UNMAPPED": 212,
        "UNSUPPORTED_TREATMENT": 21
      },
      "publicationStatus": "AVAILABLE",
      "treatmentEvidence": [
        {
          "cardCount": 433,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.998512512880448,
          "scoreInterval": null,
          "setCount": 15,
          "speciesCount": 249,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "common"
        },
        {
          "cardCount": 241,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.703140745899459,
          "scoreInterval": [
            5.648952373509402,
            5.722452462914378
          ],
          "setCount": 13,
          "speciesCount": 192,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare"
        },
        {
          "cardCount": 27,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.087790951515672,
          "scoreInterval": [
            4.916575978801813,
            5.194733609712452
          ],
          "setCount": 5,
          "speciesCount": 27,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_break"
        },
        {
          "cardCount": 143,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.963846787117581,
          "scoreInterval": [
            5.861325488290157,
            6.08395474709312
          ],
          "setCount": 14,
          "speciesCount": 116,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo"
        },
        {
          "cardCount": 129,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.362333301668031,
          "scoreInterval": [
            3.325152484348341,
            3.4029375216719355
          ],
          "setCount": 14,
          "speciesCount": 78,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_holo_ex"
        },
        {
          "cardCount": 94,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.50309530126623,
          "scoreInterval": [
            4.36588154277701,
            4.6535108937311715
          ],
          "setCount": 14,
          "speciesCount": 62,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare_ultra"
        },
        {
          "cardCount": 263,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.294809435580869,
          "scoreInterval": [
            5.252683816739388,
            5.323127157705131
          ],
          "setCount": 14,
          "speciesCount": 202,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "uncommon"
        }
      ],
      "uncoveredCards": 1033,
      "universeId": "XY"
    },
    {
      "cards": 3434,
      "coveredCards": 2658,
      "era": "Scarlet and Violet",
      "primaryBlockers": {
        "MISSING_CANONICAL_MAPPING": 610,
        "UNSUPPORTED_TREATMENT": 166
      },
      "publicationStatus": "AVAILABLE",
      "treatmentEvidence": [
        {
          "cardCount": 1038,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.012027261014038,
          "scoreInterval": [
            4.981787511903742,
            5.040544636370481
          ],
          "setCount": 16,
          "speciesCount": 501,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "common"
        },
        {
          "cardCount": 211,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.7087790709314636,
          "scoreInterval": [
            3.6717930458742534,
            3.754697793481283
          ],
          "setCount": 16,
          "speciesCount": 172,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "double_rare"
        },
        {
          "cardCount": 384,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.396307361447457,
          "scoreInterval": [
            5.295221599788409,
            5.49752999254117
          ],
          "setCount": 15,
          "speciesCount": 356,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "illustration_rare"
        },
        {
          "cardCount": 250,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.839503513843664,
          "scoreInterval": [
            2.7999198330974457,
            2.8750809605755885
          ],
          "setCount": 16,
          "speciesCount": 201,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "rare"
        },
        {
          "cardCount": 95,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 6.1432587159898455,
          "scoreInterval": [
            6.00724787702952,
            6.266331694595652
          ],
          "setCount": 15,
          "speciesCount": 85,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "special_illustration_rare"
        },
        {
          "cardCount": 141,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.37380775907147,
          "scoreInterval": [
            4.278846512857866,
            4.471222393718373
          ],
          "setCount": 14,
          "speciesCount": 135,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "ultra_rare"
        },
        {
          "cardCount": 539,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "AVAILABLE",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.972896016867434,
          "scoreInterval": [
            4.939617166834516,
            5.001863204280736
          ],
          "setCount": 16,
          "speciesCount": 361,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "uncommon"
        }
      ],
      "uncoveredCards": 776,
      "universeId": "Scarlet and Violet"
    },
    {
      "cards": 992,
      "coveredCards": 0,
      "era": "Mega Evolution",
      "primaryBlockers": {
        "INSUFFICIENT_HISTORY": 45,
        "INSUFFICIENT_UNIVERSE_SUPPORT": 88,
        "MISSING_CANONICAL_MAPPING": 204,
        "MODEL_INSTABILITY": 599,
        "UNSUPPORTED_TREATMENT": 56
      },
      "publicationStatus": "INSUFFICIENT_ERA_SUPPORT",
      "treatmentEvidence": [
        {
          "cardCount": 288,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.997539801214917,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 250,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "common"
        },
        {
          "cardCount": 88,
          "evidenceStatus": "AVAILABLE",
          "finalAvailabilityStatus": "INSUFFICIENT_ERA_SUPPORT",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 2.86662482489956,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 83,
          "temporalStatus": "MARKET_MOVEMENT",
          "treatmentKey": "double_rare"
        },
        {
          "cardCount": 101,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 7.331355374980519,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 100,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "illustration_rare"
        },
        {
          "cardCount": 72,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 5.493771971010635,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 68,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "rare"
        },
        {
          "cardCount": 45,
          "evidenceStatus": "INSUFFICIENT_HISTORY",
          "finalAvailabilityStatus": "INSUFFICIENT_HISTORY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 3.7944007503093737,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 45,
          "temporalStatus": "INSUFFICIENT_HISTORY",
          "treatmentKey": "ultra_rare"
        },
        {
          "cardCount": 138,
          "evidenceStatus": "MODEL_INSTABILITY",
          "finalAvailabilityStatus": "MODEL_INSTABILITY",
          "heterogeneityStatus": "WITHIN_GATE",
          "researchScore": 4.989059358763905,
          "scoreInterval": null,
          "setCount": 6,
          "speciesCount": 122,
          "temporalStatus": "MODEL_INSTABILITY",
          "treatmentKey": "uncommon"
        }
      ],
      "uncoveredCards": 992,
      "universeId": "Mega Evolution"
    }
  ]
}
```
