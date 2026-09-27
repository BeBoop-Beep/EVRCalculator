# E2.17E sealed OCR-v3 holdout evaluation

## Integrity and independence

The evaluator verified 43 unique and matching queue/raw/prediction row IDs, matching queue/raw card IDs and image URLs, and the frozen 43-row truth counts: JAPANESE 6, NOT_JAPANESE 36, UNCERTAIN 1. Recomputed fingerprints matched the frozen corpus (`f032b201ae2b85c16b7cb4296f5bb08c29a90d5d8a19e02a8c9e8716d770fd7d`), labels (`b3f2f23d11db6d77ed93c9ff997de6c769775a30175ce69e62a2c78299813e22`), predictions (`f0d1032df2a64eec10771eb5f153b889212904a3e2a0c347b8ce768a7c943757`), and OCR-v3 freeze (`79bed607ff3a34bf701030d5f2947048f176427010fbc34273c91588a0059756`).

Predictions were created at 2026-09-17 17:38:30 UTC; review started at 17:44:39 UTC. The prediction file's mtime precedes history writes; the history mtime precedes label freeze. Queue truth matches the last effective append-only history label for every row. The reviewer page renders only row ID, canonical card ID, and image URL. No post-seal prediction or post-freeze history mutation is apparent from the retained artifacts and timestamps. The sealed prediction artifact does not contain human truth.

## Independent holdout result

`JAPANESE_MISMATCH` is the positive veto decision. The single UNCERTAIN row is excluded from definitive metrics.

| Human truth | Mismatch | Other OCR-v3 state |
|---|---:|---:|
| JAPANESE | TP 4 | FN 2 |
| NOT_JAPANESE | FP 0 | TN 36 |

Mismatch precision **4/4 = 1.0** (Wilson 95% **0.5101–1.0**); Japanese recall **4/6 = 0.6667**; false mismatch rate **0/36 = 0**; specificity **36/36 = 1.0**. Both Japanese misses fell to `UNVERIFIED`, not `NOT_JAPANESE_EVIDENCE`. No false positives or new systematic unsafe OCR class appeared in this holdout. The small positive sample leaves wide precision uncertainty.

### Japanese misses

| Row / canonical card | OCR state / reason | Kana evidence | Hangul evidence | Confidence | Classification |
|---|---|---|---|---|---|
| `e2_17c_holdout_0014` / `209f02db-d953-4dde-bbd6-0822671fe1d1` | `UNVERIFIED` / `weak_weak_no_conflict` | 27 kana, 9 kana regions, 2 high-confidence kana | 9 raw Hangul, 0 high-confidence Hangul, 0 high-confidence Hangul regions, max run 2, max Hangul-region confidence 0.0952 | OCR succeeded; 18 regions, mean 0.1955, max 0.7116 | Weak OCR confidence; conservative kana threshold. No evidence of a crop failure in the sealed metrics. |
| `e2_17c_holdout_0024` / `c7e36a14-236f-4b93-a4a8-a4be2ddc7193` | `UNVERIFIED` / `weak_weak_no_conflict` | 88 kana, 10 kana regions, 0 high-confidence kana | 15 raw Hangul, 0 high-confidence Hangul, 0 high-confidence Hangul regions, max run 2, max Hangul-region confidence 0.0325 | OCR succeeded; 23 regions, mean 0.2607, max 0.9977 | Weak confidence on kana-bearing regions; conservative threshold. No evidence of a crop failure in the sealed metrics. |

### Uncertain truth, excluded

`e2_17c_holdout_0007` is `UNVERIFIED` (`weak_weak_no_conflict`): 70 kana, 44 kana regions, 0 high-confidence kana; 23 raw Hangul, 0 high-confidence Hangul, 0 high-confidence Hangul regions, max run 2, max Hangul-region confidence 0.3319. OCR succeeded with 124 regions, mean confidence 0.2417 and max 0.9999. No truth label was coerced.

## Policy freezes

The holdout passes the specified rejection-veto gate. LANGUAGE-v2 is frozen as a research policy: provider Korean/Chinese mismatch is authoritative; provider Japanese alone is not; OCR-v3 `JAPANESE_MISMATCH` vetoes regardless of provider value; unsupported values are unverified. LANGUAGE-v2 source SHA256 is `cf57b37d3c663ce741a573eef00fc741d9a6fb02f65228c283390bb33f0ff2a6`; freeze fingerprint is **`a858449b281de3523bd9ac2be64bbead216bb1c8da1388f93cdad38c9793d6bd`**. Its manifest includes the supported vocabulary, OCR-v3 freeze, holdout corpus/label/evaluation fingerprints, and `production_authority=false`.

COMBINED-IDENTITY-v4 applies the existing v3 combination to LANGUAGE-v2. `LANGUAGE_MISMATCH` rejects before eligibility; match/unverified preserve the prior combination and never promote. Source SHA256 is `9d0399c0825f5f83ccf1aff0c9895eabcdffb297ff6f6e391721c1f9a6cf3403`; freeze fingerprint is **`8c5e3cf2b30af626b178874db97a4cff0d4fdc8fb60186a12a72b760e7430fe4`**. It has no production authority.

## Historical post-hoc diagnostics and new-blind decision

After policy freezes, the E2.14, V4, V5, and E2.9B evidence was audited as `HISTORICAL_POST_HOC_NON_CERTIFYING`. The retained row artifacts contain neither per-row `getItem` `localizedAspects` nor sealed OCR-v3 outputs for these cohorts. Thus LANGUAGE-v2/COMBINED-v4 states, newly rejected human-YES rows, and v4 precision/coverage **cannot be computed** from retained evidence. The human review field `language=NON_ENGLISH` for E13-0127 is not a provider Language aspect and was not substituted for one. E13-0127's provider aspect, OCR-v3 result, LANGUAGE-v2 state, and COMBINED-v4 state remain **unmeasured**; its rejection is unverified.

For context only, the previously frozen E2.14 COMBINED-v2 baseline has 259 accepts, 258 true accepts, 1 false accept (E13-0127), precision 0.996139, Wilson lower 0.978458, 58/70 card coverage, and one catastrophic WRONG_LANGUAGE false accept. Earlier, separately computed v3 prospective diagnostics reported V4 203/203 true accepts, 0 false accepts, 56/70 coverage; V5 206/206, 0 false accepts, 56/70; E2.9B 185/185, 0 false accepts, 54/70. **These are not v4 diagnostics.** The E2.17E diagnostic JSON records them as baselines with v4 results null.

The new certification blind is **not justified yet**: the required E13-0127 rejection and E2.14 v4 false-accept, Wilson, coverage, and catastrophic gates have not been measured. The next step is a separate non-certifying collection/scoring pass that obtains per-row provider `Language` aspects and OCR-v3 outputs for the consumed cohorts, then applies the frozen policies without tuning. No new blind was captured.

## Tests and scope

The focused suite (`test_ebay_e2_17e_holdout_evaluation.py`, `test_ebay_e2_17c_holdout_review.py`, and `test_ebay_e2_17d1_fingerprint_repair.py`) passed **42/42**. It covers fingerprint and row-set failures, all confusion quadrants, UNCERTAIN exclusion, metric arithmetic, provider/OCR precedence, combined rejection, post-hoc classification, and absence of production writes. Both policy manifest fingerprints and source hashes independently recomputed. OCR-v3, sealed predictions, frozen labels, and existing policies were not modified. Nothing staged, committed, or pushed.

EBAY_OCR_V3_NOT_READY_HISTORICAL_DIAGNOSTIC_EVIDENCE_MISSING
