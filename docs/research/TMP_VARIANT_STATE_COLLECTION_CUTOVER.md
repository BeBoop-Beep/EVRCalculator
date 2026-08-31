# TMP Variant-State Collection Cutover

branch: `"fix/public-rankings-entitlement-regression"`

HEAD: `"00ab4279f353a1802b1a790b88d114bef567377c"`

study ID: `"tmp-variant-collection-cutover-9e396d367720a6fd"`

static blocker baseline: `{"EDITION_MISSING": 152, "SPECIAL_TREATMENT_MISSING": 680, "TREATMENT_COLLAPSED": 438}`

exact variants created/normalized: `0`

Base/WOTC variants separated: `47`

modern variants separated: `102`

provider identities resolved: `266`

provider identities unresolved: `683`

TCGPlayer edition/SKU findings: `{"conditionSemantics": "Condition remains condition_id and is never embedded in card_variant_id.", "printingSemantics": "Persisted provider payload can distinguish explicit '1st Edition Holofoil', 'Unlimited Holofoil', or 'Shadowless Holofoil' when supplied.", "productIdSemantics": "Commercial product identity only; it does not prove vintage edition.", "skuSemantics": "The current TCGPlayer source payload contains no SKU/version identifier beyond productID + printing + condition.", "verifiedBasePayload": "Base Charizard product 42382 reports printing=Holofoil and therefore has EXTERNAL_VARIANT_IDENTITY_UNAVAILABLE for edition-aware collection."}`

Base Charizard variant states: `{"card": "Charizard", "cardId": "ef4363f7-9928-4914-a8b2-cc51a37c5c46", "collectionStatus": "PROVIDER_VARIANT_IDENTITY_MISSING", "currentBlocker": "EDITION_MISSING", "currentVariantStates": [{"edition": null, "id": "040dfecb-b1ee-4ad3-8d05-7851b7a33d71", "printing_type": "holo", "special_type": null}], "desiredVariantStates": [{"edition": "1st-edition", "printing_type": "holo", "special_type": null}, {"edition": "shadowless", "printing_type": "holo", "special_type": null}, {"edition": "unlimited", "printing_type": "holo", "special_type": null}], "externalIdentities": [{"card_variant_id": "040dfecb-b1ee-4ad3-8d05-7851b7a33d71", "external_catalog_key": "BS", "external_product_id": "42382", "external_variant_key": "edition=|printing_type=holo|special_type=", "id": "f1effcd4-f086-49a4-b5dd-0a8322929b30", "provider": "tcgplayer", "source_payload": {"number": "004/102", "printing": "Holofoil", "productName": "Charizard", "rarity": "Holo Rare", "set": "Base Set", "setAbbrv": "BS"}, "source_reference": "https://www.tcgplayer.com/product/42382"}], "externalProviderEvidenceMissing": true, "firstTrustworthyDate": null, "legacyCardId": "ee211b03-5d48-4bc6-8c18-9007437b76bf", "legacyCollapsedHistoryRetained": true, "number": "4", "set": "Base", "variantIds": ["040dfecb-b1ee-4ad3-8d05-7851b7a33d71"], "waitingCanNowHelp": false}`

Base Blastoise variant states: `{"card": "Blastoise", "cardId": "8d4c21b9-d5f3-4e37-bdda-f0eb5f54c4dd", "collectionStatus": "PROVIDER_VARIANT_IDENTITY_MISSING", "currentBlocker": "EDITION_MISSING", "currentVariantStates": [{"edition": null, "id": "67f65c88-73ba-4b1b-9261-8dd8a16ec784", "printing_type": "holo", "special_type": null}], "desiredVariantStates": [{"edition": "1st-edition", "printing_type": "holo", "special_type": null}, {"edition": "shadowless", "printing_type": "holo", "special_type": null}, {"edition": "unlimited", "printing_type": "holo", "special_type": null}], "externalIdentities": [{"card_variant_id": "67f65c88-73ba-4b1b-9261-8dd8a16ec784", "external_catalog_key": "BS", "external_product_id": "42360", "external_variant_key": "edition=|printing_type=holo|special_type=", "id": "7b573251-1cba-402a-b0c9-79211c1ae3db", "provider": "tcgplayer", "source_payload": {"number": "002/102", "printing": "Holofoil", "productName": "Blastoise", "rarity": "Holo Rare", "set": "Base Set", "setAbbrv": "BS"}, "source_reference": "https://www.tcgplayer.com/product/42360"}], "externalProviderEvidenceMissing": true, "firstTrustworthyDate": null, "legacyCardId": "326df550-f355-4589-823f-050204ed4eb1", "legacyCollapsedHistoryRetained": true, "number": "2", "set": "Base", "variantIds": ["67f65c88-73ba-4b1b-9261-8dd8a16ec784"], "waitingCanNowHelp": false}`

Base Venusaur variant states: `{"card": "Venusaur", "cardId": "fb496590-6035-4ded-a836-599bceda513e", "collectionStatus": "PROVIDER_VARIANT_IDENTITY_MISSING", "currentBlocker": "EDITION_MISSING", "currentVariantStates": [{"edition": null, "id": "483ae056-958e-48c1-8d43-c2e444923c73", "printing_type": "holo", "special_type": null}], "desiredVariantStates": [{"edition": "1st-edition", "printing_type": "holo", "special_type": null}, {"edition": "shadowless", "printing_type": "holo", "special_type": null}, {"edition": "unlimited", "printing_type": "holo", "special_type": null}], "externalIdentities": [{"card_variant_id": "483ae056-958e-48c1-8d43-c2e444923c73", "external_catalog_key": "BS", "external_product_id": "42355", "external_variant_key": "edition=|printing_type=holo|special_type=", "id": "151120a5-163d-49b6-a538-ee7d2f625cd6", "provider": "tcgplayer", "source_payload": {"number": "015/102", "printing": "Holofoil", "productName": "Venusaur", "rarity": "Holo Rare", "set": "Base Set", "setAbbrv": "BS"}, "source_reference": "https://www.tcgplayer.com/product/42355"}], "externalProviderEvidenceMissing": true, "firstTrustworthyDate": null, "legacyCardId": "9cbfd274-7151-4087-81e1-e6353ac7a6c3", "legacyCollapsedHistoryRetained": true, "number": "15", "set": "Base", "variantIds": ["483ae056-958e-48c1-8d43-c2e444923c73"], "waitingCanNowHelp": false}`

scraper-routing changes: `["TCGPlayerParser receives set identity", "edition-distinct vintage sets reject edition-null provider rows", "explicit provider edition/finish/special state maps through external_variant_key", "unknown conditions are rejected rather than defaulted to Near Mint"]`

fail-closed behavior: `{"diagnostic": "EXTERNAL_VARIANT_IDENTITY_UNAVAILABLE", "editionDistinctSets": ["Base", "Fossil", "Jungle", "Team Rocket"], "genericPriceDuplicated": false, "identityConflict": "external_variant_identity_conflict", "unknownCondition": "row rejected"}`

first authoritative collection date: `null`

December collection manifest status: `{"CANONICAL_VARIANT_UNRESOLVED": 438, "COLLECTION_READY": 149, "PROVIDER_VARIANT_IDENTITY_MISSING": 683}`

tests: `["focused parser/helper/manifest selection: 38 passed", "scraper + external identity + cards routing + postcondition selection: 121 passed"]`

live verification: `{"baseCasesInspected": 5, "charizardExternalVariantKey": "edition=|printing_type=holo|special_type=", "charizardProductId": "42382", "duplicateProviderProductVariantKeys": 0, "externalKeyVariantStateMismatches": 0, "firstPostCutoverObservationPending": true, "genericVintageRowWillNowBeRejected": true, "mode": "read-only database plus controlled parser cycle", "nearMintConditionRows": [{"id": "4f8d1181-670e-4aea-937c-4d98d2e531a6", "name": "Near Mint"}], "productionWrites": 0}`

production TMP rows persisted: `0`

final readiness decision: `"TMP_VARIANT_COLLECTION_READY_FOR_DECEMBER"`

limitations: `["No provider SKU is present in the current TCGPlayer payload", "No production variants were fabricated for unsupported editions or treatments", "Scheduled scrapes must run after cutover to create observations for newly explicit provider states", "The manifest records authoritative cutover semantics; it does not retroactively split legacy observations"]`

reproducibility hash: `"de78367023c0fb86369760b71ec143cba9237947ce32f1e8a73a0e873aad6505"`
