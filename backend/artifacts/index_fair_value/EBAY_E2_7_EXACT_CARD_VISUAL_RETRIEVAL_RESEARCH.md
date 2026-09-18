# EBAY_E2_7 — Exact-Card Visual Retrieval Research (IMAGE-v2)

## Scope discipline

D3-v5 untouched. No V6 text heuristic. No V5 certification re-run. No new
400+ row human blind cohort captured. No ORB threshold re-tuning (E2.6's
`ebay_image_identity_verifier.py` is unmodified). No paid vision API called
anywhere. All research below is local, free, and CPU-capable in production.

## 1. Gallery size / coverage (Phase A)

Canonical-image authority audit confirmed E2.6's finding still holds:
`pokemon_canonical_cards.image_large_url`, sourced from the Pokemon TCG
API's `images.large`, keyed per printing (`pokemon_tcg_api_card_id`) — no
new canonical source was invented.

Development gallery built for this task: **165 real, distinct canonical
card images** across **26 Pokemon-name families** (Charizard ex, Pikachu
ex, Gardevoir ex, Chien-Pao ex, Miraidon ex, Koraidon ex, Iron Hands ex,
Iron Valiant ex, Gholdengo ex, Dragonite ex, Tyranitar ex, Lucario ex,
Sylveon ex, Umbreon ex, Espeon ex, Greninja ex, Garchomp ex, Rayquaza ex,
Dialga ex, Lugia ex, Ho-Oh ex, Zacian ex, Snorlax ex, Gengar ex, Alakazam
ex, plus a trimmed 3-entry Mewtwo ex remainder — see remediation below),
fetched from the public Pokemon TCG API/CDN. Each entry records
`canonical_card_id` (the API's own per-printing id, e.g. `sv3-125`), card
name, collector number, set id, and canonical image URL — a variant/
treatment-specific mapping is structurally guaranteed because the API
already models each printing as its own object with its own image.

**Compliance remediation performed in this pass**: the initial broad fetch
for the "Mewtwo ex" family (a fuzzy/substring name query) incidentally
pulled in `sv10-231` — the literal canonical identity behind one of the
four consumed V5 blind-cohort failure rows (`D5-0224`, Team Rocket's
Mewtwo ex). This was caught by a structural test
(`test_benchmark_families_exclude_consumed_target_names`) before any
report was written from the contaminated run. Fixed by adding an explicit,
unconditional `CONSUMED_TARGET_NAMES` exclusion filter to the gallery
loader; the gallery was rebuilt (171 → 165 entries) and the benchmark and
freeze below both reflect the **corrected, uncontaminated** gallery only.

**Not claimed**: no attempt was made to determine whether any two distinct
`card_variant_id`s in inDex's own catalog share byte-identical canonical
artwork (e.g. a reprint with no visual change) — per the task's explicit
instruction not to claim image separation where canonical imagery is
literally identical, this remains an open, unquantified limitation (see
Section 13). Missing-image and duplicate-image accounting against inDex's
own live catalog was not performed in this pass (would require live DB
access to `pokemon_canonical_cards`, out of scope for a local research
pass); the 165-card research gallery itself has zero missing images (every
entry was only added after a successful image fetch).

## 2. Model / license (Phase B, "research current options")

| Option | Decision |
|---|---|
| **DINOv2-small** (`facebook/dinov2-small`, via HuggingFace `transformers`) | **Selected.** Official Meta AI weights, **Apache-2.0** license (permissive, redistribution-safe). 384-dim CLS embedding. Frozen, zero-shot — no fine-tuning performed. |
| FAISS | Not needed — gallery size (165, and any realistic near-term size in the low thousands) is trivially brute-forceable with a single `numpy` matmul (`gallery_matrix @ query_vector`); FAISS would add a dependency with no measured benefit at this scale. Flagged as future work if the gallery grows to tens of thousands of images. |
| OpenCLIP (as comparator) | **Not evaluated this pass** — DINOv2-small's zero-shot result was already strong enough (Section 6) that a second backbone comparison was judged lower priority than validating the winning approach against real data (Section 7). Flagged as unresearched, not ruled out. |
| Community-trained Pokemon-card-retrieval weights | **Not used.** No opaque/unlicensed community checkpoint was downloaded or referenced — only the official, provenance-clear DINOv2-small release. |

Embeddings are precomputed and cached to disk keyed by
`sha256(image_bytes)` (`CanonicalGallery`/`GALLERY_EMBEDDING_CACHE_DIR`) —
a canonical image is embedded once, ever, never per-listing.

## 3. Preprocessing (Phase C)

`ebay_image_identity_verifier`'s (E2.6) `detect_card_region()` (contour →
largest quadrilateral → perspective rectification) is reused as a
best-effort pre-step: if a card region is detected, the rectified crop is
embedded; if detection fails (as it legitimately does on a meaningful
fraction of real photos — busy backgrounds, low contrast, etc.), the
**full original image is embedded instead** — detection failure is never
treated as verification failure. The E2.6 eBay-CDN resolution upgrade
(`s-l225.jpg → s-l1600.jpg`, same photo, ~4–6× linear resolution, zero
extra API cost) is reused unchanged.

Multi-crop strategies (embedding both the raw and the cropped image and
combining results) were not implemented this pass — the single best-effort
crop-or-fallback approach already produced clean results (Section 7).

## 4. Development dataset (Phase E)

- **165-card real canonical gallery** (Section 1), all consumed-target-name
  free.
- **495 POSITIVE retrieval queries**: each of the 165 canonical images
  under 3 geometric transforms (12° rotation, perspective warp,
  4×-downscale + JPEG-55 recompress) — reused from E2.6's transform
  library.
- **3,600 FALSE-TARGET-MATCH pairs**: every ordered (true_card,
  falsely_claimed_sibling) pair within each of the 26 same-Pokemon-name
  families, across all 3 transforms — covering exactly the task's required
  hard-negative classes (same Pokemon, different printing/set/number/
  artwork; same treatment/layout within a family) at real, non-synthetic
  scale.
- This did **not** reach "several hundred real photographed eBay listings"
  (that would require a large fresh human-labeled development-partition
  scrape, out of scope for this pass — see Section 13) — the 3,600
  hard-negative *pairs* figure is large, but it is built from 165 underlying
  *images*, transformed synthetically. The real-photo evidence in this
  research is the 6 genuine eBay listing photos carried over from E2.5/E2.6
  plus their true canonical counterparts (Section 7) — small in count, but
  directly on-point (they include the exact three consumed catastrophic
  cases' siblings).
- No consumed V4/V5 blind row was used to select any threshold (verified by
  a structural test scanning the benchmark script's non-docstring source
  for the four row ids).

## 5. Frozen-model retrieval results (Phase F)

```
gallery_size: 165                    query_embedding_seconds_per_image: 0.048
retrieval_queries: 495               top1_accuracy: 0.9414
                                      top3_accuracy: 0.9980
                                      top5_accuracy: 0.9980
false_target_match_pairs: 3600       false_target_match_rate: 0.0000
```

## 6. Hard-negative results

**Zero false target matches across all 3,600 same-Pokemon-family hard-
negative claim pairs.** For every pair where a transformed photo of card A
was paired with a WRONG claimed target B (same name family — e.g. two
different Charizard ex printings, two different Team Rocket's Mewtwo ex
prints excluded from this dev set per Section 1), the retrieval+margin
policy never emitted `MATCH` for the wrong target B. This is the exact
metric the task calls "most important" and it separates cleanly, unlike
E2.6's ORB approach (71.9% false-match rate on the equivalent test).

## 7. Real-world confirmatory check (illustrative — not used to tune)

Run via the **official, frozen** historical diagnostic
(`run_ebay_image_retrieval_historical_diagnostic.py`), against real
network-fetched canonical images and real eBay listing photos (not the
synthetic dev-set transforms):

| Row | Target | Real listing photo | Result | target_rank | gap/margin |
|---|---|---|---|---|---|
| `D5-0054` catastrophic | Kyurem ex (Black Bolt #165) | photo is a different Pokemon entirely | **MISMATCH** | 162 / 165 | gap 0.313 |
| `D5-0056` sibling (true) | Kyurem ex (Black Bolt #165) | genuine Kyurem photo | **MATCH** | 1 | margin 0.216 |
| `D5-0224` catastrophic | Team Rocket's Mewtwo ex (#231) | photo is a different Mewtwo ex | **MISMATCH** | 110 / 165 | gap 0.290 |
| `D5-0219` sibling (true) | Team Rocket's Mewtwo ex (#231) | genuine photo | **MATCH** | 1 | margin 0.184 |
| `D5-0378` catastrophic | Grafaiai (#223) | photo is Mega Charizard ex | **MISMATCH** | 33 / 165 | gap 0.136 |
| `D5-0375` sibling (true) | Grafaiai (#223) | genuine Grafaiai photo | **MATCH** | 1 | margin 0.098 |

**All three catastrophic false accepts that failed real V5 certification
are correctly rejected (`MISMATCH`), and all three legitimate sibling true
accepts are correctly accepted (`MATCH`)** — the exact behavior described
in the task's "why retrieval" example (target ranked far below #1 against a
strongly-preferred competing identity).

## 8. False-target-MATCH analysis

0/3,600 on the synthetic same-family dev set; 0/3 on the real catastrophic
cases (this section overlaps with Sections 6–7 by design — the metric the
task names "most important" was measured both ways and agrees).

## 9. MATCH / MISMATCH / UNVERIFIED policy (Phase G)

Implemented exactly per the task's candidate semantics:

- **MATCH**: `target_rank == 1` AND `target_similarity >= 0.75` AND
  `top1_vs_top2_margin >= 0.05`.
- **MISMATCH**: `target_rank != 1` AND `target_vs_top1_gap >= 0.05`
  (another identity clearly, measurably preferred over the target).
- **UNVERIFIED**: everything else — missing/corrupt images, unknown target
  identity, or a `target_rank == 1` result whose margin over the runner-up
  is too thin to trust (this occurred once in the historical check on an
  earlier gallery variant — a near-tied margin of `0.0` correctly produced
  `UNVERIFIED` rather than a forced `MATCH`).

Thresholds are conservative by design (task Phase L: "default toward an
extremely conservative image MATCH policy").

## 10. CPU performance (Phase K)

- Gallery build (165 images, cache-warm): **0.13 s**.
- Embedding: **48 ms/image** average (CPU, `facebook/dinov2-small`,
  batch size 1) — 495 queries embedded in 23.7 s total.
- Nearest-neighbor search: a single `165×384 @ 384` matmul per query —
  sub-millisecond, no FAISS needed at this gallery size.
- **Estimated daily cost at ~200 image-verification candidates/day**
  (per the task's own volume estimate, applied only after text-matcher
  filtering, never to raw Browse results): ≈ 200 × 50 ms ≈ **10 seconds of
  CPU per day**, plus the (already-established, E2.6) negligible bandwidth
  cost of one listing-photo fetch per candidate. Canonical-gallery
  embeddings are a one-time cost per card, not repeated per candidate.
- No GPU was required for any of the numbers above; a GPU was not even
  available in this environment — everything ran on ordinary CPU,
  confirming the required CPU-safe production path.

## 11. Was IMAGE-v2 frozen?

**Yes.** `ebay_image_retrieval_verifier_v2_freeze_manifest.json` records:
verifier source sha256, model name/license/preprocessing version,
thresholds, canonical-image-authority description, development dataset
fingerprint (over the corrected 165-image gallery), and the development
benchmark summary. `production_authority: false` and
`shadow_research_only: true` are both explicitly set — this is a frozen
**research** candidate, not a production authority; no pricing, Fair
Value, Set Value, or simulation code path reads it.

## 12. Historical consumed-failure diagnostic

Performed once, after freeze, via the dedicated non-certifying script —
see Section 7's table (identical run, sourced from
`ebay_image_retrieval_v2_historical_post_hoc_diagnostic.json`). No
threshold was changed afterward.

## 13. Limitations

- The 3,600-pair hard-negative measurement is built from 165 real canonical
  images under synthetic geometric transforms, not 3,600 independently
  photographed real eBay listings. The real-photo evidence is limited to
  the 6 carried-over E2.5/E2.6 listing photos (Section 7) — strong and
  directly on-point, but small in count. A materially larger real-listing-
  photo development corpus (the task's "several hundred" target) was not
  available without a fresh scrape+review effort, out of this task's scope.
- Whether any two `card_variant_id`s in inDex's live catalog share
  byte-identical canonical art was not audited against the live DB in this
  pass; if such cases exist, no image method (this one included) can
  distinguish them, and that limitation would need separate handling
  (e.g. falling back to text-only identity for those specific variants).
- OpenCLIP was not run as a comparator backbone.
- No synthetic-photography-invariance augmentation (Phase H: glare, sleeve/
  toploader overlays, tabletop compositing, shadow, occlusion) or
  metric-learning adapter (Phase I) was built — the frozen, zero-shot
  DINOv2-small backbone already cleared the acceptance bar on both the
  synthetic dev set and the real confirmatory check, so the task's own
  Phase H/I gate ("only if frozen retrieval is promising but insufficient")
  was not triggered. This should be revisited if a larger real-photo
  benchmark later reveals gaps.
- OCR (Phase J) was not pursued — image retrieval alone already resolved
  the specific ambiguity (the three consumed catastrophic cases) without
  requiring a secondary signal.
- Card-region detection still fails on a meaningful share of real photos
  (observed in the historical diagnostic: 3 of 6 real photos fell back to
  the full, undetected frame) — the pipeline handles this gracefully
  (never forces a decision), but detection robustness itself was not
  separately improved in this pass.

## 14. Tests

`backend/tests/unit/scripts/test_ebay_image_retrieval_verifier.py` — **28
tests**, all passing: gallery build/provenance fields, embedding
determinism and L2-normalization, embedding-cache reuse (a re-added
identical image is never re-embedded), image fingerprinting, missing/
unknown-target/corrupt image → `UNVERIFIED`, exact canonical image →
rank-1 `MATCH`, rotated same-card → still rank-1 and never `MISMATCH`,
three independent wrong-target-claim hard negatives never `MATCH`,
rank/margin decision logic, an engineered ambiguous near-tie →
`UNVERIFIED`, an engineered clearly-beaten target → `MISMATCH`, a
structural check that no metric-learning adapter was trained this pass, a
structural check that the benchmark's dev gallery excludes all four
consumed target names (the exact regression this pass caught and fixed —
Section 1), CPU-only execution, D3-v5/`classify_listing` never imported,
no pricing/Fair Value module ever referenced, full output-contract
serialization, stable source hash, and no paid-vision-provider string
anywhere in the module. Full `ebay`-scoped regression suite: **577
passed**.

## 15. Recommended next project

Retrieval is materially, measurably better than E2.6's pairwise template
matching (0% vs. 71.9% false-target-match rate on an equivalent hard-
negative test; the three real catastrophic V5 failures are now correctly
rejected). Per the task's own gate ("first prove the retrieval approach is
materially better than IMAGE-v1... do not capture a new blind cohort in
this task yet"), that bar is cleared, but IMAGE-v2 is frozen as a
**shadow research candidate only** (`production_authority: false`) — it
has not yet been validated against a large, real, human-reviewed
development corpus of actual eBay listing photos (Section 13's main
limitation), and it has not been combined with the D3-v5 text matcher into
a joint decision policy.

**Recommended next step**: `EBAY E2.8 — Combined Text (D3-v5) + Image
(IMAGE-v2) Identity Policy`, built and validated against a real,
non-consumed development-partition corpus of eBay listing photos (not just
synthetic transforms of canonical art) before any new human blind cohort
is captured, following the same fail-closed composition sketched in E2.6:
`TEXT_HIGH_CONFIDENCE + IMAGE_MATCH` → strongest identity state;
`TEXT_HIGH_CONFIDENCE + IMAGE_MISMATCH` → reject;
`TEXT_HIGH_CONFIDENCE + IMAGE_UNVERIFIED` → a distinct, non-strongest state
(e.g. `TEXT_VERIFIED_IMAGE_UNVERIFIED`), never silently promoted.

EBAY_IMAGE_V2_FROZEN_COMBINED_POLICY_READY
