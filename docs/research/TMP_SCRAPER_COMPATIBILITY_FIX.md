# Scraper Compatibility Fix After TMP Variant Cutover

1. **branch:** `"fix/public-rankings-entitlement-regression"`

2. **HEAD:** `"04a87555bf3723afd63dd38905bc801765d8ea98"`

3. **original compatibility problem:** `"Base generic provider rows were rejected, risking a zero-card daily scrape failure."`

4. **parser policy before:** `{"strictEditionRequired": ["Base", "Jungle", "Fossil", "Team Rocket"]}`

5. **parser policy after:** `{"marketFallbackAllowed": ["Base"], "strictEditionRequired": ["Jungle", "Fossil", "Team Rocket"]}`

6. **Base generic-row behavior:** `"Accepted as MARKET_ONLY_AMBIGUOUS_VARIANT on the generic edition-null variant."`

7. **Base explicit-edition behavior:** `"Accepted as EXACT_PROVIDER_VARIANT and never collapsed into generic Base."`

8. **Jungle behavior:** `"Generic rejected; explicit edition accepted."`

9. **Fossil behavior:** `"Generic rejected; explicit edition accepted."`

10. **Team Rocket behavior:** `"Generic rejected; explicit edition accepted."`

11. **market-only diagnostic:** `5`

12. **exact-variant diagnostic:** `0`

13. **rejected-variant diagnostic:** `0`

14. **Base payload card count:** `5`

15. **Base attempted price count:** `5`

16. **Base positive NM observations:** `5`

17. **source variant count:** `5`

18. **reconciled source variant count:** `5`

19. **postcondition result:** `"PASS"`

20. **zero-card gate result:** `"PRESERVED: PRINTED_TOTAL with zero payload cards remains failure."`

21. **batch-completeness compatibility:** `"Base produces legitimate nonzero generic NM observations; batch definition unchanged."`

22. **TMP manifest state for generic Base:** `{"marketCollectionStatus": "MARKET_ONLY_AMBIGUOUS", "tmpVariantCollectionStatus": "PROVIDER_VARIANT_IDENTITY_MISSING"}`

23. **explicit edition TMP state if present:** `"Explicit editions remain TMP-eligible only when provider identity is exact."`

24. **external conflict behavior:** `"external_variant_identity_conflict remains fatal."`

25. **unknown-condition behavior:** `"Unknown condition rejected; never mapped to Near Mint."`

26. **tests executed:** `["focused parser/helper/compatibility-manifest selection: 44 passed", "daily scraper + runner + dispatcher + batch + identity + postcondition regression selection: 209 passed"]`

27. **controlled Base scrape result:** `{"acceptedExactVariantGroups": 0, "acceptedMarketOnlyAmbiguousVariantGroups": 5, "cardsScraped": 5, "mode": "provider-shaped Base parser fixture plus live read-only persistence authority", "positiveNmObservationCount": 5, "postconditionResult": "PASS", "priceRowsAttempted": 5, "productionWrites": 0, "reconciledSourceVariantCount": 5, "rejectedExternalVariantIdentityUnavailable": 0, "setsFailed": 0, "setsSucceeded": 1, "sourceVariantCount": 5}`

28. **files changed:** `["backend/Scraper/helpers/card_helper.py", "backend/Scraper/parsers/tcgplayer_parser.py", "backend/Scraper/services/orchestrators/tcg_player_orchestrator.py", "backend/tests/unit/scraper/helpers/test_card_helper.py", "backend/tests/unit/scraper/test_tcgplayer_external_identity.py", "backend/scripts/build_tmp_variant_collection_cutover.py", "docs\\research\\tmp_reassessment_variant_collection_manifest.json", "docs\\research\\TMP_VARIANT_STATE_COLLECTION_CUTOVER.md", "backend/Scraper/dtos/ingest_dto.py", "docs\\research\\TMP_SCRAPER_COMPATIBILITY_FIX.md"]`

29. **production TMP rows persisted:** `0`

30. **final December readiness decision:** `"DECEMBER_TMP_COLLECTION_COMPATIBLE_WITH_DAILY_SCRAPER"`
