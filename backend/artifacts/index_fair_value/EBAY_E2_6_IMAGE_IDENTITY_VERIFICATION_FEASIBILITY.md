# EBAY_E2_6 — Image-Only Identity Verification Feasibility

## Scope discipline

D3-v5 is untouched. No V6 text heuristic was written. No V5 certification
was re-run. No new 400-row blind cohort was captured. No consumed blind row
(`D4-0375`, `D5-0054`, `D5-0224`, `D5-0378`) was used to select or tune any
threshold below — thresholds were fixed against an independent development
dataset (Section 3) before those four rows were touched at all, and the one
place they appear afterward (Section 7) is an illustrative, explicitly
non-tuning confirmatory check, not a certifying or threshold-setting step.
No paid vision API, image-matching SaaS, or billed cloud service was called
anywhere in this task.

## 1. Canonical-image authority (audit)

- `pokemon_canonical_cards` (`backend/scripts/ingest_pokemon_canonical_cards.py`)
  stores `image_small_url` / `image_large_url`, sourced verbatim from the
  Pokemon TCG API's `images.small` / `images.large` fields, keyed by
  `pokemon_tcg_api_card_id`. **This is inDex's existing canonical card-image
  authority** — no new source was invented.
- The Pokemon TCG API models each **printing/treatment as its own card
  object** (its own `id`, its own images) — e.g. `sv10-231` (Team Rocket's
  Mewtwo ex, Destined Rivals, #231, Special Illustration Rare) is a
  distinct object from any other Mewtwo ex printing. So yes: **exact
  variant/treatment does have a distinct canonical image**, provided the
  `card_variant_id → pokemon_tcg_api_card_id` join used elsewhere in the
  repo stays intact.
- The underlying CDN (`https://images.pokemontcg.io/{setId}/{number}_hires.png`)
  is directly, publicly fetchable with no API key and no billing for the
  volumes this task or any realistic candidate-verification workload would
  need.

## 2. Listing-image authority (audit)

- The E1/D3 eBay evidence capture pipeline (`ebay_d3_v5_fresh_blind_queue.csv`
  and the underlying evidence collector) retains exactly **one** image field
  per listing: `image_url`, an `i.ebayimg.com` thumbnail — observed at
  **~160×225 to 225×225 pixels**, ~15–25 KB.
- **New finding (free, zero-extra-call)**: eBay's own CDN accepts a same-
  photo resolution upgrade by swapping the filename suffix —
  `s-l225.jpg → s-l1600.jpg` returns the identical photo at full resolution
  (measured: 986×1386px, ~450–720 KB, for the exact rows below) with no
  additional Browse API call and no additional cost. This is implemented as
  `upgrade_ebay_image_url()` in the verifier and should be adopted
  everywhere a listing thumbnail is used for anything image-based.
- No additional Browse item-detail multi-image field is currently captured
  or exercised by this pipeline; whether `item.additionalImages` would add
  further useful angles was **not investigated in this pass** (flagged as
  unexplored, not as negative) — the URL-suffix upgrade alone already
  closes most of the resolution gap for free.
- No image-retention/license constraint beyond what the existing eBay
  evidence-collection work already documents was found specific to images;
  none of this task's fetching persists eBay photos anywhere beyond a
  bounded local cache (Section 5).

## 3. Development image dataset (NOT the consumed blinds)

Built from **30 freely-licensed public Pokemon TCG API card images**
across three families — `Charizard ex` (10 printings), `Pikachu ex` (10),
`Gardevoir ex` (10) — **deliberately non-overlapping** with `Kyurem ex`,
`Team Rocket's Mewtwo ex`, `Grafaiai`, and `Roaring Moon ex` (the four
consumed-failure target cards). Verified structurally by a test
(`test_benchmark_dataset_families_do_not_overlap_consumed_failure_cards`).

- **150 POSITIVE pairs**: each canonical image against 5 geometric
  transforms of itself (±8–12° rotation, perspective warp, 4× downscale +
  JPEG-55 recompress + upscale, 8% crop) — simulating photographed
  distortion while remaining, by construction, the same printed card.
- **135 HARD NEGATIVE pairs**: every same-family pairwise combination
  (e.g. `sv3-125` Charizard ex vs `sv3pt5-6` Charizard ex) — the exact
  "same Pokemon, different card/set/number/artwork" class the task
  requires, including several genuinely near-duplicate reprint templates.
- **3 EASY NEGATIVE pairs**: one cross-family pair per family combination
  (Charizard ex vs Pikachu ex, etc.).

Dataset fingerprint function (`dataset_fingerprint()`) hashes each image's
id + byte size; recorded in the benchmark output
(`ebay_image_identity_verifier_v1_dev_benchmark.json`).

## 4. Methods compared

| Method | Status |
|---|---|
| **A. ORB + ratio test + RANSAC homography** | Implemented, benchmarked (primary candidate) |
| **B. Perceptual hash (dHash)** | Implemented as a secondary diagnostic field only, never sole authority (per spec) |
| **C. Local embeddings (CLIP/OpenCLIP)** | **Not implemented this pass** — flagged explicitly as optional future research; building and validating a local embedding model was judged out of this task's effort budget given (A) already produced a clear, well-evidenced answer |
| **D. Card-region detection** | Implemented (contour → largest quadrilateral → perspective rectification), folded into the pipeline as a best-effort pre-step; falls back to the full image on any failure |

All of A/B/D are 100% local, CPU-only, free/open-source
(`opencv-python-headless`, `numpy`, `Pillow`). No paid API of any kind was
called.

## 5. Image download / cache layer

Implemented in `ebay_image_identity_verifier.fetch_image_bytes()`:

- Deterministic cache key = `sha256(url)`, one file per key under
  `backend/artifacts/index_fair_value/ebay_image_identity_cache/`.
- 10-second fetch timeout; 8 MB hard size cap (oversized bodies rejected,
  not truncated-and-kept); content-type allowlist
  (`image/jpeg`, `image/png`, `image/webp`); corrupt/undecodable bytes
  decode to `None` rather than raising.
- **No infinite retry**: a failed fetch writes a `.failed` marker so a
  second call for the same URL returns `None` immediately instead of
  re-hitting the network (verified by
  `test_fetch_failure_is_cached_as_a_failure_marker_and_not_retried`).
- Any fetch/decode failure on either side becomes `UNVERIFIED`, never a
  guessed state.

## 6. Development benchmark results

```
positive_pairs: 150            positive_match_rate: 1.000   positive_unverified_rate: 0.000
hard_negative_pairs: 135       hard_negative_false_match_rate: 0.7185   <-- FAILS the acceptance bar
easy_negative_pairs: 3         easy_negative_false_match_rate: 0.000
```

Raw ORB+RANSAC-homography **inlier ratio is not discriminative** for this
hard-negative class: different-but-related card printings share enough
templated graphic design (holographic border, HP/energy iconography, text
box layout, same-artist illustration conventions) that RANSAC finds a
homography explaining dozens to hundreds of "inlier" matches on the shared
template elements alone — independent of whether the central artwork is
the same card. Measured hard-negative `homography_inlier_ratio` ranged
0.073–0.992, with a **median of 0.75**, overlapping heavily with the
positive-pair range (0.90–0.99).

An ad hoc ablation (center-cropping both images to the central 55% before
matching, to exclude border/frame template) reduced but did **not**
eliminate the problem: hard-negative false-match rate at a 0.6 ratio
threshold fell from ~68% to ~24%, still far above the "zero or near-zero"
acceptance bar, and it was **not adopted** (would require re-tuning against
the same dev set, and still fails the bar).

An absolute-inlier-count-only threshold (ignoring ratio) fares better in
isolation on this synthetic dev set (≈6% false-match rate at a count of
~459) — but this number is an artifact of how the positive pairs were
constructed (a full-resolution image against a geometric transform of
*itself* naturally yields thousands of well-distributed matches that a
real photographed listing will not reproduce). It was not adopted as the
production rule; Section 7 shows why.

## 7. Confirmatory real-world check (illustrative only — NOT used to tune)

To sanity-check the dev-set finding against genuine deployment inputs, the
already-fixed implementation (thresholds unchanged from Section 6) was run
**once**, read-only, against the real canonical Pokemon TCG API images for
the two consumed target cards that have a public canonical entry, paired
with their real (hi-res-upgraded) eBay listing photos:

| Canonical | Listing | Expected | Result | good / inliers / ratio |
|---|---|---|---|---|
| `zsv10pt5-165` Kyurem ex (Black Bolt) | `D5-0056` (genuine true accept) | MATCH | **MATCH** | 253 / 242 / 0.957 |
| `zsv10pt5-165` Kyurem ex (Black Bolt) | `D5-0054` (catastrophic false accept — different Pokemon entirely) | must NOT be MATCH | **MATCH** ❌ | 35 / 16 / 0.457 |
| `sv10-231` Team Rocket's Mewtwo ex | `D5-0219` (genuine true accept) | MATCH | **MATCH** | 370 / 340 / 0.919 |
| `sv10-231` Team Rocket's Mewtwo ex | `D5-0224` (catastrophic false accept — different Mewtwo ex) | must NOT be MATCH | UNVERIFIED | 20 / 8 / 0.400 |

This reproduces, on real data, exactly the catastrophic failure mode the
image guard exists to prevent: **`D5-0054` — a photo of an entirely
different Pokemon than Kyurem — clears the MATCH bar** (16 inliers, 0.457
ratio, both barely above threshold) purely from shared special-illustration-
rare border/frame/text-layout features. This was not used to adjust any
threshold; it independently corroborates the dev-set verdict using the
actual motivating rows.

No verifier was frozen, so `run_ebay_image_identity_historical_diagnostic.py`
(the proper historical post-hoc mode) was **not exercised as an official
diagnostic run** — it correctly refuses via `DiagnosticBlocked` with no
freeze manifest present (verified by
`test_historical_diagnostic_refuses_without_a_frozen_manifest`). This
section's table is a manual, explicitly-labeled illustrative check, kept
separate from that mechanism.

## 8. Legitimate historical controls

Both real true-accept sibling rows tested (`D5-0056`, `D5-0219`) correctly
scored MATCH — the method does **not** simply reject everything; it fails
specifically and reproducibly on the hard-negative/catastrophic class,
which is the failure mode that actually matters.

## 9. Runtime / cost

- ORB feature extraction + matching + RANSAC on real hi-res (~1000×1400px)
  images: **~51 ms/pair** measured (20-run average).
- Card-region detection: **~6 ms/pair**.
- Total: **~57 ms per listing-candidate verification** on ordinary CPU.
- At the estimated volume (70-card cohort, ~200 accepted candidates/day):
  ≈ 200 × 57 ms ≈ **11.4 seconds of CPU per day** — negligible.
- Bandwidth: canonical images cached once per card (≈500–700 KB each,
  70 cards ≈ 35–50 MB total, one-time); listing images ≈500 KB × 200/day
  ≈ 100 MB/day — trivial and free on any standard hosting tier.
- Cache hit rate: canonical images should approach 100% after the first
  cohort pass (same URL reused across every candidate for that card);
  listing images are inherently cache-miss-once (each listing is unique).

## 10. Selected verifier / freeze

**No candidate was frozen.** Per the task's explicit acceptance bar ("zero
or near-zero false MATCH on meaningful development negatives... precision
dominates coverage"), a method producing a 71.9% false-MATCH rate on
same-Pokemon hard negatives — and reproducing the exact catastrophic
failure on real data — does not meet the bar. `ebay_image_identity_verifier.py`
exists as built, tested infrastructure (fetch/cache, ORB pipeline, region
detection, output contract) for future iteration, but its current
thresholds are **not** production-authoritative and no freeze manifest
(`ebay_image_identity_verifier_v1_freeze_manifest.json`) was written.

## 11. Limitations

- The core failure mode — shared template/border/holo-pattern features
  across different printings of visually similar rarity tiers — is a
  structural property of ORB-style local feature matching on graphic-design-
  heavy objects, not a tuning error. Fixing it plausibly requires either
  (a) precise artwork-region segmentation that excludes the card frame
  entirely (non-trivial without per-card bounding-box ground truth), or
  (b) a learned embedding specifically trained/fine-tuned for exact-card
  discrimination (well beyond "zero-shot CLIP cosine similarity," which the
  task itself warns is too coarse for this).
- CLIP/OpenCLIP was not evaluated in this pass (Section 4, Method C) —
  genuinely unresearched, not ruled out.
- The Browse API's additional-image fields were not investigated.
- The development dataset, while real and free of any consumed-blind
  contamination, is necessarily small (30 canonical cards, 3 families) —
  a larger dev corpus might reveal a viable region-segmentation threshold
  that this pass's ablation did not find.

## 12. Tests

`backend/tests/unit/scripts/test_ebay_image_identity_verifier.py` — **32
tests**, all passing: canonical/listing fetch, cache hit avoids re-fetch,
deterministic cache keys, corrupt image → `UNVERIFIED`, simulated timeout
never raises and is not retried, missing image → `UNVERIFIED`, identical
image → `MATCH`, downscale/recompress/rotate/perspective-warp of the same
image never produces a false `MISMATCH`, unrelated-image pairs never
produce `MATCH`, no paid-provider imports/strings anywhere in the module,
deterministic repeated output, output contract carries every required
diagnostic field, `embedding_similarity` stays `None` this pass, the
benchmark script's dataset never overlaps the four consumed failure cards,
the historical diagnostic runner is labeled `NON_CERTIFYING_...` and
refuses cleanly without a freeze manifest, D3-v5/`classify_listing` are
never imported by the image module, and the eBay CDN URL upgrade helper is
covered directly. Full `ebay`-scoped regression suite: **549 passed**.

## 13. Recommended next project

Per the task's decision fork:

> If local image verification is NOT viable: report that clearly. Then we
> can decide whether to use item-detail/manual verification only, keep
> eBay asks as diagnostic/non-authoritative evidence, or stop pursuing
> eBay as Fair Value input.

**Recommendation: keep eBay listing evidence diagnostic/non-authoritative
for image-only-identity-risk cases for now.** The text matcher (D3-v5)
remains the frozen baseline and continues to be useful for everything except
this specific, now well-characterized residual risk class. Do not proceed
to `EBAY E2.7 — Combined Text + Image Identity Policy + New Blind
Certification` on the basis of this pass's ORB/homography candidate. A
future attempt would need either a genuinely different local method
(artwork-only segmentation, or a fine-tuned local embedding) evaluated
against a materially larger development dataset before any new 400-row
blind cohort is justified.

EBAY_IMAGE_VERIFICATION_NOT_VIABLE_HARD_NEGATIVE_FALSE_MATCH_RATE
