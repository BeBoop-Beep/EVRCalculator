# EBAY E2.16C -- Japanese Aspect Validation + LANGUAGE-v2 / COMBINED-v4 Freeze Decision

**Status: DEVELOPMENT ONLY. `development_only=true`, `production_authority=false`. Not a certification. Does not modify D3-v5, IMAGE-v2, CAPTURE-ALLOCATION-v2, the frozen/consumed E2.14 certification, the frozen LANGUAGE-v1 contract, or frozen COMBINED-IDENTITY-v3.**

Analysis code: `backend/scripts/ebay_e2_16c_japanese_language_aspect_validation.py`
Tests: `backend/tests/test_ebay_e2_16c_japanese_language_aspect_validation.py` (29 passed)

---

## 1. Phase A -- precondition results

All 12 preconditions were independently recomputed from the real, now-completed E2.16B artifacts (not assumed from the task's forward-guessed numbers):

| # | Precondition | Result |
|---|---|---|
| 1 | corpus row count = 150 | PASS -- 150 rows in `ebay_e2_16b_japanese_language_development_queue.csv` |
| 2 | corpus fingerprint matches frozen manifest | PASS -- recomputed `38636c3ff0a6b907d464430f57c16520fa5f28c00150389a0cf4f9962591ab9b` == manifest `corpus_fingerprint` |
| 3 | label fingerprint deterministically computable | PASS -- recomputed independently from `review_history.jsonl` via last-non-undone-label-per-`row_id` (identical logic to `reconstruct_effective_labels()` in `ebay_e2_16b_japanese_language_development_review_server.py`): `06d68834b284e12ff97bf1461573a18f71c6acac372015eca84eda9a7c3f2e30` |
| 4 | labels complete (150/150, none missing) | PASS -- every queue row resolves to a final label; `missing_labels == []` |
| 5 | freeze marker / session-ended signal | PASS -- manifest has an explicit freeze mechanism (`labels_frozen: true`, `freeze_timestamp: 2026-09-16T20:14:04.589935+00:00`, materialized `human_truth_label` column already written into the queue CSV by the server's own `--freeze` path) |
| 6 | actual human counts (recomputed) | ENGLISH = 52, NON_ENGLISH = 97, UNCERTAIN = 1 (150 total) |
| 7 | `development_only = true` | PASS |
| 8 | `production_authority = false` | PASS |
| 9 | raw-internal row IDs match queue rows exactly | PASS -- 150/150 `row_id`s in `ebay_e2_16b_japanese_language_development_raw_internal.jsonl` set-equal to the queue |
| 10 | no post-freeze label mutation | PASS (by construction) -- recomputed label fingerprint from the raw history equals the manifest's frozen `label_fingerprint` exactly, and equals the fingerprint of the already-materialized queue CSV; history events are internally timestamp-monotonic per row and none exist after the freeze timestamp |
| 11 | E2.16A frozen LANGUAGE-v1 source/fingerprint unchanged | PASS -- `backend/scripts/ebay_e2_16a_language_aspect_validation.py` and `EBAY_E2_16A_LANGUAGE_ASPECT_VALIDATION.md` are untouched by this task (confirmed via `git status --short`: both untracked-but-unmodified since this worktree's start; no edits made) |
| 12 | COMBINED-v3 unchanged | PASS -- `backend/scripts/ebay_combined_identity_policy_v3.py` not modified |

**Originally forecast vs. actually computed:** the task's caller-stated forward-guess numbers (fingerprint `38636c3ff0a6b907d464430f57c16520fa5f28c00150389a0cf4f9962591ab9b`, label fingerprint `06d68834b284e12ff97bf1461573a18f71c6acac372015eca84eda9a7c3f2e30`, ENGLISH=52/NON_ENGLISH=97/UNCERTAIN=1, 150 rows) turn out to match the independently recomputed values **exactly, with no discrepancy**. This was verified by computation, not assumed.

**All preconditions pass. Proceeding to Phase B onward.**

---

## 2. Frozen human counts

- Total rows: 150
- ENGLISH: 52
- NON_ENGLISH: 97
- UNCERTAIN: 1
- Definitive rows (ENGLISH + NON_ENGLISH): 149

---

## 3. Provider-Japanese row count

Across all 150 rows, the provider `Language` aspect (raw value `"Japanese"`, normalized `JAPANESE`) is present on **92 rows** (matches the manifest's `JAPANESE_ASPECT_PRIMARY` stratum size of 92 exactly). Full normalized-language distribution across all 150 rows:

| Normalized value | Count |
|---|---|
| JAPANESE | 92 |
| ENGLISH | 30 |
| UNKNOWN (aspect absent) | 27 |
| OTHER_NON_ENGLISH (raw "Indonesian") | 1 |

---

## 4. Japanese TP / FP / UNCERTAIN

Within the 92 provider-JAPANESE rows:

| Human truth | Count |
|---|---|
| NON_ENGLISH (TP) | 90 |
| ENGLISH (FP) | 2 |
| UNCERTAIN | 0 |

- TP = 90
- FP = 2
- Uncertain-provider-Japanese = 0

---

## 5. Japanese-aspect precision

`precision = TP / (TP + FP) = 90 / 92 = 0.97826` (97.83%)

---

## 6. Wilson 95% interval

`wilson_ci(90, 92) = (0.9242, 0.9940)` -- lower bound **92.42%**, upper bound **99.40%**.

---

## 7. False-mismatch rate

Definitive human-ENGLISH rows in the corpus: **52**.
`false_mismatch_rate = Japanese-FP / definitive-ENGLISH = 2 / 52 = 0.03846` (**3.85%**).

For comparison, the E2.16A-frozen KOREAN/CHINESE contract required **0** false mismatches among 197 definitive rows before being deemed safe. A 3.85% false-mismatch rate against the ENGLISH population is materially non-zero.

---

## 8. Non-English recall breakdown

Across all 97 human-NON_ENGLISH rows:

| Provider signal | Count |
|---|---|
| provider JAPANESE | 90 |
| provider KOREAN | 0 |
| provider CHINESE | 0 |
| other explicit non-English language | 0 |
| provider ENGLISH | 0 |
| missing/unknown Language aspect | 7 |

Japanese-specifically: of 97 human-NON_ENGLISH rows, 90 are caught by the Japanese aspect (recall = 90/97 = 92.8%); 7 are missed because the `Language` aspect is simply absent from that listing's `getItem` response (no contradicting or wrong value -- just no structured evidence). No Korean/Chinese/other-language rows exist in this Japanese-focused development corpus by construction (it was purpose-built to stress-test Japanese only), so this corpus supplies no new counter-evidence against the existing frozen KOREAN/CHINESE inclusion, and no new positive evidence for any language besides Japanese either. Recall/coverage is context only; precision remains the veto-critical metric per the task spec.

---

## 9. Every Japanese false positive (individually inspected)

### FP 1 -- `e2_16b_dev_0033` (item `v1|336759241465|0`)

- **Target card:** Archeops (SV11W: White Flare)
- **Title:** "Pokemon TCG Archeops 130/086 SV11W: White Flare Holo Art Rare **Japanese**"
- **Human truth:** ENGLISH (physical card/photo judged English)
- **Provider Language aspect:** `Japanese` (normalized JAPANESE)
- **Sampling stratum:** JAPANESE_ASPECT_PRIMARY
- **Seller country (context only, not evidence):** US
- **Images:** 6 image URLs retained (multiple angles of what appears to be a single physical card)
- **localizedAspects:** 13 aspects retained, including `Set = SV11W: White Flare`, `Card Number = 130/086`, `Card Name = Archeops`, `Language = Japanese`. No other aspect contradicts the Language value; the aspect table is internally *consistent* with itself (Language=Japanese is the only language-relevant field, and nothing else in the aspect list says English).
- **Multiple cards in listing?** No evidence in the retained aspects/title of multiple SKUs.
- **Provider aspect copied from another SKU/variant?** Plausible but not provable from structured evidence alone -- the **title itself** independently asserts "Japanese," so this is not simply an internal metadata inconsistency; the seller's own title agrees with the aspect. The human reviewer's ENGLISH call therefore implies either (a) the physically photographed card is English despite title+aspect both claiming Japanese (a genuine seller template/copy error spanning both title and structured data), or (b) an edge-case reviewer judgment call on a visually ambiguous listing. Either way, this is **not** a case where structured metadata alone is internally self-contradictory -- title and aspect *agree* with each other and both disagree with the human-judged photo. This is a different and, from a metadata-only perspective, a **harder-to-detect** failure mode than E2.16A's row `e2_16_dev_0153` (where the aspect was wrong but nothing else, including the title, echoed it).

### FP 2 -- `e2_16b_dev_0050` (item `v1|257726067754|0`)

- **Target card:** Jolteon ex (SV: Prismatic Evolutions)
- **Title:** "Jolteon ex Holo Double Rare SV: Prismatic Evolutions 030/131 NM" -- **no language cue anywhere in the title**
- **Human truth:** ENGLISH
- **Provider Language aspect:** `Japanese` (normalized JAPANESE)
- **Sampling stratum:** JAPANESE_ASPECT_PRIMARY
- **Seller country (context only):** US
- **Images:** 2 image URLs retained
- **localizedAspects:** 15 aspects retained, including `Country/Region of Manufacture = Japan`, `Country of Origin = Japan`, `Illustrator = 5ban Graphics`, `Language = Japanese`. These fields are *mutually consistent with each other* (a card manufactured in Japan legitimately carries `Country of Origin: Japan` even when it is an English-language print -- essentially all modern Pokemon TCG cards, English included, are physically manufactured in Japan). The `Language: Japanese` value appears to be a seller template/auto-fill error that conflated manufacturing origin with printed language, not an internal contradiction detectable from the aspect set itself.
- **Multiple cards in listing?** No evidence of multiple SKUs.
- **Systematic pattern?** This row shares **zero title-level cue** with FP 1 -- there is no "Japanese" word anywhere for a human or a machine to notice pre-hoc. This is the harder of the two failure modes: a wholly silent, title-invisible aspect error.

**Comparison to the E2.16A original Japanese FP (`e2_16_dev_0153`):** E2.16A's single FP had root cause `PROVIDER_ASPECT_WRONG` -- an isolated, unexplained aspect error with a title that gave no corroborating signal either way (title said "Reshiram ex 158/086 White Flare", no "Japanese" word). That is structurally closest to this round's FP 2 (`e2_16b_dev_0050`). FP 1 (`e2_16b_dev_0033`) is a **new pattern** not observed in E2.16A: the title itself independently echoes "Japanese," meaning the metadata error is not confined to the structured aspect field alone. Two false positives across 92 Japanese-aspect rows, with **two distinct underlying mechanisms**, is a stronger and differently-shaped signal than E2.16A's single isolated FP.

---

## 10. Provider-consistency signal investigation (Phase F)

Per the spec, only investigated because Japanese FPs exist:

- **Language aspect contradicting another explicit structured aspect?** No -- in both FPs, the aspect table is internally self-consistent (FP 2's Country-of-Origin=Japan does not contradict Language=Japanese; they reinforce each other, incorrectly, against the human-judged photo).
- **Multiple incompatible language values in one item's localizedAspects?** No -- neither FP row carries more than one language-bearing value.
- **Duplicated/copy-pasted aspect pattern across unrelated variants?** Cannot be confirmed from the retained single-item evidence; plausible for FP 1 (title+aspect both say Japanese, suggesting a shared bulk-listing template used across a seller's Japanese and English inventory) but not provable, and even if true, it would not be machine-detectable from this listing's own data -- it would require cross-listing comparison infrastructure that does not exist today.
- **Item-detail metadata internally inconsistent with canonical target identity?** No -- `Set`, `Card Number`, `Card Name` all correctly identify the target card in both FPs; only `Language` is wrong.
- **Multiple variants/cards in one listing?** No evidence of this in either FP.

**Finding: no safe, generalizable, machine-detectable consistency rule exists that would catch both FPs without also risking false rejections on true-positive Japanese rows.** FP 1 could in principle be caught by a "title literally contains a foreign-language word that a human might use to cross-check" heuristic, but the spec explicitly forbids using title text as language evidence (Phase F: "Do NOT use ... English title alone as proof of language" -- and by the same logic, a title word cannot be used to *contradict* the aspect either, since title is categorically excluded as evidence in either direction). FP 2 has **no signal at all** outside the aspect table itself, so no rule operating on structured metadata could have caught it. There is no single detectable pattern that spans both.

---

## 11. LANGUAGE-v2 decision (Phase G)

Per Phase G's conservative standard, Japanese may be added only if (1) a meaningful number of provider-Japanese rows are human-confirmed NON_ENGLISH (TRUE -- 90/92), (2) observed false-mismatch behavior is sufficiently safe, (3) no recurring unexplained provider-metadata failure mode makes provider JAPANESE inherently unreliable, (4) any proposed consistency guard is generalizable and independently supported, (5) unsupported cases remain UNVERIFIED.

Criterion 1 is met. Criteria 2-4 are **not** met:

- **Criterion 2 (safe false-mismatch behavior):** a 3.85% false-mismatch rate against the definitive-ENGLISH population (2/52), with a Wilson precision lower bound of only 92.4%, is not "sufficiently safe" for a hard rejection veto -- this is a *reject* action applied to a real English-target listing, and unlike LANGUAGE_UNVERIFIED (which never rejects), a false LANGUAGE_MISMATCH directly and wrongly removes an eligible English card from consideration.
- **Criterion 3 (no recurring unexplained failure mode):** two false positives exist, and they are **not** the same failure mode -- one is title-corroborated (metadata error visible even in the title), one is title-silent (only visible in structured aspects, riding alongside self-consistent-but-wrong Country-of-Origin data). Two independently-arising, unexplained mechanisms across only 92 samples is a *recurring* and *unresolved* failure pattern, not an isolated one-off like E2.16A's single FP.
- **Criterion 4 (generalizable, supported consistency guard):** Phase F found no safe, generalizable, machine-detectable rule that covers both FPs (see Section 10). Title-based cross-checking is explicitly disallowed by the spec, and even if it were allowed, it would not catch FP 2.

Per the spec's explicit instruction ("Do NOT add Japanese merely because aggregate precision is high -- one unexplained false positive can be enough to withhold the veto"), and given this round surfaced **two** unexplained, differently-caused false positives rather than one, **LANGUAGE-v2 is NOT frozen. Japanese is NOT added to the authoritative mismatch vocabulary.**

LANGUAGE-v1 (`{KOREAN, CHINESE}`) and COMBINED-IDENTITY-v3 remain frozen and unchanged, exactly as before this task. No LANGUAGE-v2 or COMBINED-v4 artifact is produced.

---

## 12. LANGUAGE-v2 fingerprint

Not applicable -- LANGUAGE-v2 was not frozen (Section 11). No fingerprint is minted.

---

## 13. COMBINED-v4 fingerprint

Not applicable -- COMBINED-v4 was not created, per Phase I's condition ("only if LANGUAGE-v2 freezes"). COMBINED-IDENTITY-v3 remains the frozen, unmodified combined policy.

---

## 14. E2.14 post-hoc result

Not run. Phase K is explicitly conditioned on "only if LANGUAGE-v2/COMBINED-v4 freeze" -- since neither froze this round, no post-hoc diagnostic against E2.14's consumed cohort was executed. For context (unchanged from E2.16A, verified in Section 1 precondition 11): under the still-frozen KOREAN/CHINESE-only LANGUAGE-v1 / COMBINED-v3, E2.14's known catastrophic Japanese WRONG_LANGUAGE row (`E13-0127`, item `v1|407215142815|0`) remains **not rejected** by any currently-frozen policy, because its provider `Language: Japanese` aspect is still classified `LANGUAGE_UNVERIFIED` (Japanese is still outside the authoritative vocabulary). This is unchanged by this task's findings.

---

## 15. V4/V5/E2.9B diagnostics

Not run, for the same reason as Section 14 (Phase K gate not met -- no new frozen policy artifact exists to diagnose against). These cohorts remain exactly as previously characterized in their own reports; this task made no changes to them.

---

## 16. OCR decision (Phase J)

**Yes, OCR-v1 research is now justified.** The evidence from this round meaningfully sharpens the case beyond E2.16A's single isolated FP:

- Structured provider metadata alone (the `Language` aspect) **cannot** safely close the Japanese failure class as currently observed -- two independent false-positive mechanisms exist within a 92-row Japanese-aspect population, one of which (`e2_16b_dev_0050`) leaves **no detectable trace anywhere in title or structured metadata** other than the wrong `Language` value itself paired with self-consistent (but misleading) Country-of-Origin data.
- The recurring, unexplained nature of these failures (two different mechanisms in two rounds of development sampling -- E2.16A's `PROVIDER_ASPECT_WRONG` and this round's two further cases) indicates this is not converging toward a single, fixable root cause via more structured-metadata sampling alone.
- Because a false MISMATCH is a hard reject (unlike UNVERIFIED, which only costs recall), and because the false-mismatch rate (3.85%) is materially above what a conservative reject-veto should tolerate, **repeated Japanese provider false positives remain with no safe detectable metadata-consistency rule** -- which is exactly the condition under which the task spec says to recommend OCR.

Recommendation: begin OCR-v1 research as a candidate path to close the Japanese (and broader non-English) failure class where structured metadata is silent or wrong, per Phase J.

---

## 17. Next certification decision

**Not justified yet.** Per Phase L, a new blind certification requires (1) Japanese safely added or another robust solution closing the Japanese failure class, (2) no new safety regressions from post-hoc diagnostics, (3) E2.14's known catastrophic Japanese row actually blocked, (4) coverage >= 80%. None of (1)-(3) are satisfied this round: Japanese was not added, no alternative solution was implemented, and E2.14's catastrophic row remains unblocked under the still-frozen policy. Per the spec's explicit instruction, do **not** recommend another 500-row blind while the exact known Japanese failure remains unaddressed.

---

## 18. Tests

`backend/tests/test_ebay_e2_16c_japanese_language_aspect_validation.py` -- **29 passed**, covering (at minimum) all 22 required areas: frozen corpus fingerprint, label fingerprint determinism, UNCERTAIN exclusion, Japanese TP, Japanese FP, Japanese precision, Japanese false-mismatch rate, provider-Japanese+human-English conflict forensics (both FP rows individually identified with distinct root causes), missing-language -> UNVERIFIED, unsupported-French -> UNVERIFIED, Korean/Chinese preserved authoritative (no counter-evidence in this corpus), Japanese-only-if-freeze-criteria-pass (explicitly asserted NOT met), LANGUAGE-v2 fingerprint determinism (structural), COMBINED-v4/v3 mismatch-veto semantics, MATCH/UNVERIFIED fall-through preserved, no title-based veto (structural source check), no country/marketplace inference (structural + `FORBIDDEN_EVIDENCE_FIELDS` check), consumed-cohort-diagnostic-only (E2.14 artifact untouched), no production writes (structural source check), and latest-label-wins resolution correctly handling the `e2_16b_dev_0000` relabel (ENGLISH -> NON_ENGLISH) plus a generic relabel+undo case.

```
$ python -m pytest backend/tests/test_ebay_e2_16c_japanese_language_aspect_validation.py -q
29 passed
```

Reference fingerprints computed by the analysis module (informational, not frozen since no v2/v4 artifact exists):
- `corpus_fingerprint` (E2.16B): `38636c3ff0a6b907d464430f57c16520fa5f28c00150389a0cf4f9962591ab9b`
- `label_fingerprint` (E2.16B, recomputed): `06d68834b284e12ff97bf1461573a18f71c6acac372015eca84eda9a7c3f2e30`
- `confusion_matrix_fingerprint` (sha256 of sorted `row_id:normalized_language:human_truth`): `d1f81ccc8ad580386fce8496acef2852d64f33741c63ddf66881ca5bd6d6e6ad`

---

## 19. Next step

Begin OCR-v1 scoping research (Phase J recommendation) as the path to close the Japanese-language false-accept class, since structured `getItem` `Language` aspect metadata alone has now shown two independent, unexplained false-positive mechanisms across two rounds of development sampling and cannot be safely trusted as a hard-reject veto for Japanese. Do not attempt a further structured-metadata-only development round for Japanese without first exhausting what OCR can add; do not schedule a new blind certification until either OCR (or another robust mechanism) demonstrably closes E2.14's known catastrophic Japanese row.

---

## 20. Do-not-list confirmation

No frozen human labels were modified. LANGUAGE-v1 and COMBINED-IDENTITY-v3 source files were not modified. D3-v5, IMAGE-v2, and CAPTURE-ALLOCATION-v2 were not touched. E2.14 was not rewritten or re-certified. No Fair Value, Explorer, or E3 code was touched. No prices were published. Nothing was staged, added, committed, pushed, merged, rebased, reset, or synced (`git status --short` shows only pre-existing untracked worktree files plus the two new files this task created: this report and the analysis/test scripts -- confirmed no `git add`/`commit` was ever run).

---

EBAY_JAPANESE_LANGUAGE_ASPECT_NOT_SAFE_RECOMMEND_OCR_V1
