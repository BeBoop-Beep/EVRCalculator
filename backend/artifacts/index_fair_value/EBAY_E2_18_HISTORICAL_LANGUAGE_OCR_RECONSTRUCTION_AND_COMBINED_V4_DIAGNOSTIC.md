# E2.18 historical language/OCR reconstruction and COMBINED-v4 diagnostic

All four cohorts are **HISTORICAL_POST_HOC_NON_CERTIFYING**. Frozen OCR-v3, LANGUAGE-v2, COMBINED-v4, D3-v5, IMAGE-v2, and human labels were not changed. The new-blind decision is **NO-GO** because E13-0127 remains a false accept and E2.14 fails its false-accept and Wilson gates.

## 1. Exact IMAGE-v2 authority and frozen stack

On canonical `develop`, `backend/scripts/ebay_image_retrieval_verifier.py` has raw SHA256 `f72f5d964f792815bf92ef5f24cda7d8f9d83c2d1bcdb64ea0ebd9fcf252d446`, exactly the original IMAGE-v2 freeze hash and the SHA256 of Git blob `24d7eebfbd4a482c9f35997dc4d772af7e918ed0`. The prior CRLF worktree differed only by line endings; the current LF working-tree file equals that blob byte-for-byte. The strict source-hash gate was not altered. Focused IMAGE-v2 tests: **28 passed**. See `EBAY_E2_18A_IMAGE_V2_EXACT_BYTE_AUTHORITY_RESTORATION.md`.

The scoring gate also verified OCR-v3 source `9194795896f57a78f1fcc4ee2bb6d421b084fd318e7afb9c7cfb98db1cbac668`, LANGUAGE-v2 source `cf57b37d3c663ce741a573eef00fc741d9a6fb02f65228c283390bb33f0ff2a6`, COMBINED-v4 source `9d0399c0825f5f83ccf1aff0c9895eabcdffb297ff6f6e391721c1f9a6cf3403`, D3-v5 rule `93301e5da1cf8129896993f12cfec2b66c5c887d679cb6f0755785c884581c69`, and canonical-resolution artifact `9fc36d8df60c77196d28075b9c8a878bd00467014ba072d037df184ab295d446` against their recorded authorities. CAPTURE-ALLOCATION-v2's three dependency source fingerprints and allocation fingerprint were also verified. Allocation-v2 was not used to score these retained rows.

## 2. Evidence inventory and bounded reconstruction

Each queue retained a listing ID and image URL for every row. The corresponding retained raw item-summary records also covered every listing ID, but none contained `getItem` `localizedAspects`. No language was inferred from title, marketplace, seller country, item location, or human review fields.

| Cohort | Rows / listing IDs / image URLs | `getItem` attempts | Provider Language observed | Image fetch + OCR successful | Both sources | Neither |
|---|---:|---:|---:|---:|---:|---:|
| E2.14 | 553 / 553 / 553 | 199 unique rows; 200 calls including the earlier E13-0127 probe | 159 (158 English, 1 Japanese) | 553 | 159 | 0 |
| V4 | 420 / 420 / 420 | 0 | 0 | 420 | 0 | 0 |
| V5 | 417 / 417 / 417 | 0 | 0 | 417 | 0 | 0 |
| E2.9B | 414 / 414 / 414 | 0 | 0 | 414 | 0 | 0 |

All 199 stored E2.14 `getItem` attempts returned HTTP 200; 40 had no recognized Language aspect. The 200-call task budget was then exhausted, so other provider fields are explicitly unavailable. All 1,804 historical image fetches returned HTTP 200 and the frozen OCR-v3 code decoded them successfully. OCR-v3 decisions were E2.14: 535 `UNVERIFIED`, 18 `NOT_JAPANESE_EVIDENCE`; V4: 411/9; V5: 414/3; E2.9B: 408/6. **No historical image produced `JAPANESE_MISMATCH`.** The retained listing URLs served low-resolution images; E13-0127 yielded only one JA OCR region. This limits the veto's historical recall and is not evidence for changing its frozen thresholds.

LANGUAGE-v2 `UNVERIFIED` row counts were E2.14 **395**, V4 **420**, V5 **417**, E2.9B **414**. For E2.14, 394 rows lacked a provider Language aspect and had no authoritative OCR mismatch; E13-0127 had provider Japanese, which alone is nonauthoritative. Provider evidence loss is substantial, especially for the three older cohorts. Their clean post-hoc results cannot be treated as a new certification or as proof of full provider-language coverage.

## 3. Sealing order and E13-0127

Evidence reconstruction projected only row ID, listing ID, and image URL. The COMBINED-v4 scorer used frozen D3-v5/IMAGE-v2 states, frozen policy implementations, and reconstructed provider/OCR evidence without reading human truth. It saved and SHA256-fingerprinted each cohort's prediction artifact before a separate function opened the human-review queue. Prediction fingerprints: E2.14 `fb5e03cb58cccd448f65ac9a8019fc5137dba3a681f0c2a5e381e4abc4a69e57`; V4 `be91187dd51dea76a2abf2aad34f03eb8f4021a266e17d388d513a6860dee8e3`; V5 `50abc617b118486cc682b36e2dc4c322332c740fd153442554bdafd4ca899849`; E2.9B `d429f2d36a589c5aa46c152ffc469f93f88fe46cada847918d52c74a59530894`. All four recomputed after sealing.

E13-0127 (`v1|407215142815|0`) returned provider Language **Japanese** (HTTP 200). Its retained image URL returned HTTP 200; frozen OCR-v3 returned **UNVERIFIED**, `weak_weak_no_conflict` (1 JA region, 3 kana, 0 high-confidence kana, 0 high-confidence Hangul regions). LANGUAGE-v2 returned **LANGUAGE_UNVERIFIED**. Frozen D3-v5 was `HIGH_CONFIDENCE`, IMAGE-v2 `UNVERIFIED`, so COMBINED-v4 returned **TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED**, **eligible=true**. Human truth is **NO / WRONG_LANGUAGE**. It remains the one catastrophic false accept. The earlier single-row probe was independently sealed before its truth join; the full-cohort prediction agrees.

## 4. Post-hoc diagnostics

| Cohort | Accepted | True / false accepts | Precision | Wilson 95% lower | Coverage / 70 | Catastrophic false accepts | Newly rejected human-YES | Newly accepted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E2.14 | 259 | 258 / 1 | 0.996139 | 0.978458 | 58 / 70 (0.828571) | 1: E13-0127 | 0 | 0 |
| V4 | 203 | 203 / 0 | 1.0 | 0.981428 | 56 / 70 (0.80) | 0 | 0 | 0 |
| V5 | 206 | 206 / 0 | 1.0 | 0.981694 | 56 / 70 (0.80) | 0 | 0 | 0 |
| E2.9B | 185 | 185 / 0 | 1.0 | 0.979658 | 54 / 70 (0.771429) | 0 | 0 | 0 |

V4/V5 lacked retained per-row D3-v5/IMAGE-v2 predictions, so those states were recomputed label-blind using the frozen implementations and canonical gallery. E2.14/E2.9B reused sealed per-row base predictions. The v4 language veto never promotes eligibility, so no newly accepted row is expected or observed. No older cohort shows a newly introduced catastrophic false accept. The older cohorts' Wilson/coverage limitations are reported without recertifying them.

## 5. Decision, tests, and next step

E2.14 fails the required **false accepts = 0**, **catastrophic false accepts = 0**, **Wilson lower ≥ 0.98**, and **E13-0127 rejected** gates. Its precision and 58/70 coverage do meet their respective thresholds. The absence of provider-language evidence for most rows further limits the historical diagnostic. One final fresh certification blind is **not justified** under the frozen stack.

Focused IMAGE-v2/E2.17/E2.18 suite: **109 passed**. No thresholds, models, frozen policies, human labels, or production paths were modified. A future remedy needs a separate development and independent-validation lane; it must not retune the frozen stack against this consumed row. Nothing staged, committed, or pushed by this task.

EBAY_COMBINED_V4_NOT_READY_E13_0127_STILL_FALSE_ACCEPT
