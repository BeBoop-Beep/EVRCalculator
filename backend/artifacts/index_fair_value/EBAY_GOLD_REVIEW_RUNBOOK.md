# eBay D2H Human Review Runbook

Run from the repository root:

`python -m backend.scripts.ebay_gold_review_server --partition DEVELOPMENT --reviewer YOUR_ALIAS`

Review only the displayed identity evidence. Never use price, Fair Value, TCGplayer price, or a matcher prediction. The tool intentionally hides all of them.

`EXACT_TARGET_MATCH` means the listing is the exact English, raw collectible identity: same card, set, collector number, and required edition/finish/stamp/parallel. Same Pokémon in another set is `WRONG_SET`; a similar number token that is not the target is `WRONG_CARD_NUMBER`; the same card with a different parallel is `RELATED_BUT_WRONG_VARIANT`. Slabs are `GRADED`, Japanese or other languages are `WRONG_LANGUAGE`, multi-card offers are `LOT_OR_BUNDLE`, and packs/accessories are `SEALED_OR_ACCESSORY`. Use `AMBIGUOUS` when the available evidence cannot resolve identity—do not guess.

Keys: `1` exact, `2` wrong variant, `3` wrong set, `4` wrong number, `5` wrong language, `6` graded, `7` lot/bundle, `8` sealed/accessory, `9` condition ineligible, `0` ambiguous, `O` other, `S` skip, `N` note, `U` undo. Labels auto-advance.

Use HIGH confidence only when the evidence is decisive. LOW-confidence and ambiguous decisions require a second reviewer. Preserve reviewer 1 and reviewer 2 events; adjudication adds a third event and never overwrites either label. Future matcher disagreements and every final-test false positive also require review.

Development labels may guide matcher construction. Validation labels may only select thresholds/policy. Final labels remain sealed from matcher-development code until matcher logic, thresholds, code commit, version, and fingerprint are frozen.
