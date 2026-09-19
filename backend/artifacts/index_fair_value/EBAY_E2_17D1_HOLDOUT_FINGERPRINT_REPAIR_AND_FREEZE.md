# E2.17D1 holdout fingerprint repair and human label freeze

## Defect and repair

The builder recorded SHA256 of UTF-8 `|`-joined, sorted `row_id:listing_item_id` strings. The review server previously recomputed sorted `row_id:canonical_card_id` strings, yielding a false mismatch. The server now loads the retained raw JSONL, joins it to the queue by `row_id`, and applies the builder's listing-ID contract. The manifest's original corpus fingerprint was preserved.

Before any freeze write, the server requires exactly 43 unique IDs in each of the queue, raw artifact, and sealed prediction artifact; identical row-ID sets; matching queue/raw `row_id`, `canonical_card_id`, and `image_url`; a nonblank raw `listing_item_id`; the original corpus fingerprint; and review-history IDs confined to the cohort with all 43 effective labels present. Any failure refuses freeze.

## Cohort and seal integrity

The queue and raw artifact had identical ordered row IDs (`e2_17c_holdout_0000` through `0042`), canonical card IDs, and image URLs. No predictor-relevant field difference was found. The queue's pre-freeze raw SHA256 was `ab5d9018eafb863dadd2ff0104db097499e76f685bd3723a3225375e8be43254`; its human-label columns were blank. The retained raw artifact supplied the listing IDs and recomputed the unchanged corpus fingerprint `f032b201ae2b85c16b7cb4296f5bb08c29a90d5d8a19e02a8c9e8716d770fd7d`.

The 43 sealed prediction row IDs equal the frozen human row IDs. The prediction fingerprint recomputed as its existing value, `f0d1032df2a64eec10771eb5f153b889212904a3e2a0c347b8ce768a7c943757`. Its embedded OCR-v3 freeze fingerprint matches the unchanged freeze manifest: `79bed607ff3a34bf701030d5f2947048f176427010fbc34273c91588a0059756`. Predictions were sealed before review and were not regenerated. The reviewer page does not load them.

## Tests and freeze

Focused suite: `python -m pytest backend/tests/test_ebay_e2_17c_holdout_review.py backend/tests/test_ebay_e2_17d1_fingerprint_repair.py -q` — **24 passed**. Regression cases cover matching builder/server contracts, mutable human fields, CRLF/LF, retained manifest hash, missing/extra raw rows, canonical ID/image/listing ID changes, and queue/prediction membership changes.

Executed `python backend/scripts/ebay_e2_17c_holdout_review_server.py --freeze --reviewer donny`. Output recorded 43 rows, reviewer `donny`, `development_holdout=true`, `production_authority=false`, and counts **JAPANESE=6, NOT_JAPANESE=36, UNCERTAIN=1**. The new human-label fingerprint is `b3f2f23d11db6d77ed93c9ff997de6c769775a30175ce69e62a2c78299813e22`; it was independently recomputed from the frozen queue. The history remained append-only and unchanged (SHA256 `30873e30eaa5a8dc5915f930acb0b0aa0495e69ff8ee3bc06c1d2eb7726de657`).

The frozen labels and sealed predictions are ready for E2.17E evaluation. No OCR-v3 versus human-truth evaluation was performed here. Nothing staged, committed, or pushed.

EBAY_E2_17_HOLDOUT_FROZEN_READY_FOR_OCR_V3_EVALUATION
