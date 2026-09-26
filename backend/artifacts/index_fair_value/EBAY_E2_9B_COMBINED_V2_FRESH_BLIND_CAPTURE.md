# EBAY_E2_9B — COMBINED-IDENTITY-v2 Fresh Blind Capture + Review Prep

**Final result:** `EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_READY_FOR_HUMAN_LABELING`

## 1. Worktree / branch / HEAD

- Worktree: `D:\EVRCalculator-ebay-e2.9`
- Branch: `feature/ebay-e2.9-image-veto-tiered-identity`
- HEAD: `aee7f131` (unchanged this task; E2.9/E2.9A/E2.9B all uncommitted)
- No `git add`/`commit`/`push`/`pull`/`merge`/`rebase`/`reset`/`sync` performed.

## 2. Frozen fingerprints (verified before any eBay call)

| Layer | Fingerprint | Match vs. frozen manifest |
|---|---|---|
| D3-v5 (`rule_fingerprint()`) | `93301e5d...4581c69` | ✓ matches `ebay_combined_identity_v2_freeze_manifest.json` |
| IMAGE-v2 (`source_sha256()`) | `bf50ee1f...4c680ea1` | ✓ matches; also `git diff --quiet HEAD` on the file is clean |
| COMBINED-IDENTITY-v2 (`policy_source_hash()`) | `59e32c0a...9954abf07` | ✓ matches |
| Canonical-resolution manifest (durable copy) | `9fc36d8d...ab295d446` | ✓ (Section 3) |

All four verified equal before the live capture ran. No mismatch occurred; nothing was stopped.

## 3. Durable canonical-resolution provenance

- **Original file located:** `C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e28_canonical_targets\resolve_manifest.json` (the exact path `run_ebay_combined_identity_historical_diagnostic.RESOLVE_MANIFEST_PATH` and E2.9A both used). Confirmed to still exist on disk (82,555 bytes; scratch directories on this machine are not session-scoped/auto-deleted).
- **Original SHA256:** `9fc36d8df60c77196d28075b9c8a878bd00467014ba072d037df184ab295d446`
- **Durable copy:** `backend/artifacts/index_fair_value/ebay_image_v2_canonical_resolution_manifest.json` (byte-for-byte `cp`, no transformation)
- **Durable-copy SHA256:** `9fc36d8df60c77196d28075b9c8a878bd00467014ba072d037df184ab295d446` — **identical**
- **`diff` result:** no output (byte-for-byte identical, confirmed with both `sha256sum` and `diff`)
- **Timestamp of durable copy:** `2026-09-15T02:33:07Z`
- Contents were **not** modified, regenerated, or reconstructed — 140 entries covering all V4+V5 canonical targets, unchanged. (Its `image_path` fields still point into the same scratch directory for the downloaded canonical PNGs themselves — only the manifest JSON was asked to be made durable, and only the JSON was copied. This residual fragility is noted, not fixed, per the "do not modify its contents" instruction; if that scratch directory is ever cleared, only the JSON's *mapping* survives durably, not the cached canonical image bytes it points to.)

No `EBAY_E2_9B_BLOCKED_CANONICAL_RESOLUTION_PROVENANCE` — byte equality established.

## 4. Capture start/end

- `capture_started_at`: **2026-09-15T02:37:52Z**
- `capture_finished_at`: **2026-09-15T02:40:50Z** (~3 minutes)
- Real, live eBay Browse API calls (OAuth client-credentials against `api.ebay.com`, credentials from `frontend/.env.local`, sanitized error handling — no secret ever printed/logged).

## 5. eBay request count

**225 Browse requests, 225 successful, 0 failed, 0 retries.** All 70 targets in the `d1_70` cohort completed (`--no-match`, so the matcher never ran during collection — collection itself was policy-blind by construction, not just the later sampling step).

## 6. Raw listings retrieved

**11,729** raw (deduplicated-by-item-ID-within-run) listing records across all 70 targets, written to `backend/artifacts/index_fair_value/ebay_evidence_runs/8fae557e560448009b8793ac50fe764a.raw.jsonl`.

## 7. Historical exclusions

Exclusion pool built from every file anywhere in the repo carrying a real `listing_item_id` from D2/D3/V4/V5 (E2.6–E2.9A performed no new capture of their own — they only re-consumed these same rows, so this file set is exclusion-complete for all of D2, D3, V4, V5, E2.6, E2.7, E2.8, E2.9, E2.9A):

| Source file | Historical IDs contributed |
|---|---|
| ebay_manual_gold_labels.csv | 1,050 |
| ebay_gold_development.csv | 450 |
| ebay_gold_validation.csv | 250 |
| ebay_gold_final_blind.csv | 350 |
| ebay_d3_blind_review_queue.csv | 704 |
| ebay_d3_coverage_blind.csv | 420 |
| ebay_d3_fresh_observations.csv | 9,591 |
| ebay_d3_precision_blind.csv | 300 |
| ebay_d3_v3_coverage_certification_rows.csv | 420 |
| ebay_d3_v3_high_false_positive_forensics.csv | 5 |
| ebay_d3_v3_precision_certification_rows.csv | 300 |
| ebay_d3_v4_fresh_blind_queue.csv (consumed V4 cohort) | 420 |
| ebay_d3_v5_fresh_blind_queue.csv (consumed V5 cohort) | 417 |
| ebay_d2m_second_review_queue.csv (ID recovered from `item_url`) | 192 |

**Historical ID pool size (deduplicated): 11,134.**

**Known, honestly-flagged limitation:** `ebay_d2f_final_blind_predictions.csv` and `ebay_d2v_validation_predictions.csv` predate both `listing_item_id` and `item_url` tracking (title-only schema) and **cannot be exactly ID-excluded**. This is a real, pre-existing schema gap in the oldest D2 evidence, not something silently dropped — it is named explicitly in the capture manifest's `historical_ids_not_exact_excludable_title_only_files` field.

- **Exact ID exclusions:** 9,016 raw rows excluded (item ID already in the 11,134-ID historical pool)
- **Relist/near-duplicate fingerprint exclusions:** 53 raw rows excluded (title+seller+canonical-card+price-bucket hash already seen historically)
- **Duplicate-within-this-run exclusions:** 0
- **Surviving (eligible) rows after all exclusion:** **2,660**

## 8. Relist/image exclusions — verification

Re-verified independently after sampling, using each sampled row's **real price** from its raw-evidence record (matching the exact fingerprint the capture script used, not a weaker post-hoc approximation): **0 of the final 414 rows match any historical relist fingerprint.** (An earlier self-check using `price=None` on both sides produced a misleading 77 — that was a flaw in my verification script, not in the actual exclusion logic; corrected and re-run against the real capture-time inputs.)

## 9. Final row count / unique-card count

- **Final row count: 414** (target was ~420)
- **Unique target cards represented: 69 / 70**
- **Missing card:** `640cd931-d97f-4173-ad9d-3ab86f91d92c` (Pecharunt ex, Shrouded Fable #93) — diagnosed exactly: all 30 raw listings found for this target were already historical evidence (100% excluded), a genuine current-market-availability limit, not a bug. This is exactly the "~6/card **where availability permits**" contingency the task anticipated.

## 10. Per-card distribution

**69 of 69 represented cards have exactly 6 rows each** (69 × 6 = 414). No card is under- or over-represented among those that could be filled at all.

## 11. Image infrastructure availability (Section 7 — infrastructure check ONLY, no IMAGE-v2 execution)

- Listing `image_url` present: **414 / 414** (100%)
- Random 15-row sample: real HTTP fetch + magic-byte decode check — **15 / 15 succeeded** (valid JPEG/PNG)
- Canonical target image resolution: all **69 / 69** unique cards in this cohort already have a `found: true` entry in the durable canonical-resolution manifest (Section 3) — no new resolution needed, no gaps.
- **IMAGE-v2 was not executed** against any row in this queue — confirmed by the queue schema (Section 13) containing no image-verifier output columns, and by `capture_ebay_e2_9b_fresh_blind.py` never importing `ebay_image_retrieval_verifier` or `ebay_combined_identity_policy_v1/v2`.

## 12. Queue schema

`ebay_e2_9b_fresh_blind_queue.csv` columns (kept byte-identical to the proven V4/V5 reviewer schema rather than a narrower one — see Section 14 for why):

```
benchmark_row_id, listing_item_id, item_url, listing_title, condition, condition_id,
category_id, buying_options_json, seller_id, image_url, canonical_card_id, card_variant_id,
target_card_name, target_set_name, target_card_number, target_treatment,
exact_match_yes_no_uncertain, single_card_or_lot, raw_or_graded, card_or_sealed_nonshcard,
collector_number_consistency, set_consistency, language, variant_treatment,
reviewer_id, label_timestamp, review_note, adjudicated_result
```

Row IDs: `E9B-0000` … `E9B-0413`.

## 13. Proof model outputs are absent

- `assert_no_forbidden_columns()` (checks for `matcher_version, matcher_state, identity_state, match_status, confidence, confidence_tier, score, accepted, rejection_reason, v3_state, v4_state, reason`) run against the live 414-row queue: **passes, zero forbidden columns present.**
- `capture_ebay_e2_9b_fresh_blind.py` imports only `ebay_gold_access` and the V4 capture helpers (raw-evidence loading, dedup, stratified sampling, reviewer-row building) — it does not import `ebay_d3_matcher_v5`, `ebay_image_retrieval_verifier`, or either combined-identity policy module anywhere.
- The raw evidence itself was captured with `--no-match`, so no matcher output exists anywhere in the pipeline to leak.
- All 414 `exact_match_yes_no_uncertain` values are blank (Section pre-label check #6).

## 14. Review-session ID

**`e2_9b_session_1`** — recorded as `active_review_session_id` in `ebay_e2_9b_fresh_blind_manifest.json`. This is a **new, first** session (no predecessor to invalidate); the invalidate/reset machinery from V5's server is retained as a *capability* for a possible future defect, not because one occurred here.

Review server: `backend/scripts/ebay_e2_9b_blind_review_server.py` — a direct adaptation of the corrected V5 review server (`ebay_d3_v5_blind_review_server.py`), reusing its navigation/undo/relabel/session-history architecture verbatim; only path constants, row-count expectation (414), and session-ID strings were changed. **Compatibility fix made along the way:** the queue was initially built with a narrower 2-column label schema (`exact_match_yes_no_uncertain` + `primary_no_reason` only), which broke the reused server's row-materialization step on first check (it expects the proven, already-tested 8-field internal schema — which, importantly, V5's own `derive_fields()` already derives entirely from one primary answer + one required NO-reason, so this is not a heavier reviewer burden, just a wider *storage* schema). The queue was rebuilt with the byte-identical V4/V5 `REVIEWER_FIELDS` schema and the capture re-verified deterministic (identical `cohort_fingerprint` before and after the fix, confirming the schema change did not alter row selection).

V5's `NO_REASONS` taxonomy already matches Section 10's required 9-value list **exactly** (`WRONG_CARD, WRONG_CARD_NUMBER, WRONG_SET, WRONG_VARIANT_OR_TREATMENT, GRADED, LOT_OR_BUNDLE, SEALED_OR_NON_CARD, WRONG_LANGUAGE, OTHER`) — no change needed there.

## 15. reviewed_count = 0

Confirmed in `ebay_e2_9b_fresh_blind_manifest.json`: `"reviewed_count": 0`, `"labels_exist": false`, `"labels_frozen": false`. No history file exists yet at `ebay_e2_9b_fresh_blind_review_history.jsonl` (`session_history_path(get_active_session_id()).exists()` → `False`).

## 16. Navigation/Undo/relabel tests

Rather than a manual browser click-through (not possible from this environment, and not how the original V5 navigation/image-sync defect was actually caught and fixed either — it was via automated tests), the full **99-test** suite that validates V5's reviewer server logic was adapted (import target + row-count literals only, zero logic changes) into `test_ebay_e2_9b_blind_review_server.py` and run against the real `ebay_e2_9b_blind_review_server.py` module:

```
python -m pytest backend/tests/unit/scripts/test_ebay_e2_9b_blind_review_server.py -q
99 passed in 6.56s
```

This exercises, against the actual E2.9B module: append-only history, resume/reconstruct effective state, undo (including "undo targets most recent row, not the currently-displayed row" — the exact class of bug the V5 session-1 defect was), full undo→relabel→restart cycles, freeze refusal on incomplete/mismatched/forbidden-column cohorts, all 9 NO-reason mappings, correction-queue/relabel audit flow, and page-rendering content checks. Additionally, direct checks against the **real** 414-row queue (not synthetic test fixtures):

| Check | Result |
|---|---|
| First row (`E9B-0000`) renders, contains its own row ID + image URL | ✓ |
| Middle row (`E9B-0207`) renders, contains its own row ID + image URL | ✓ |
| Last row (`E9B-0413`) renders, contains its own row ID + image URL | ✓ |
| Row IDs unique | ✓ (414/414) |
| `listing_item_id` unique (no duplicate final listings) | ✓ (414/414) |
| All human-label fields blank | ✓ (414/414) |
| Historical exact-ID leaks in final cohort | **0** |
| Relist-fingerprint leaks in final cohort (verified with real price) | **0** |

## 17. Cohort fingerprint

**`b95c4d2de079ea4a4107ca9f204176a91007c28dea0b025b3e51126a720d1b4c`**

Computed independently twice — once by the capture script at build time, once by `ebay_e2_9b_blind_review_server.cohort_fingerprint()` reading the written CSV back — and confirmed **identical** both times, including after the schema fix in Section 14 (proving the fix did not change row selection).

## 18. Test results

```
test_ebay_e2_9b_blind_review_server.py ......  99 passed in 6.56s
```

Plus the E2.9/E2.9A suites (unaffected, not re-run destructively but still present and passing from prior work in this worktree): `test_ebay_combined_identity_policy_v2.py` (28 passed), `test_ebay_e2_9a_exact_card_coverage.py` (present from E2.9A).

## 19. Exact command Donny should run to start human review

```
cd D:\EVRCalculator-ebay-e2.9
python -m backend.scripts.ebay_e2_9b_blind_review_server
```

(Mirrors exactly how `ebay_d3_v5_blind_review_server.py` is launched — opens a local server and browser window pointed at row 1 of the 414-row queue, session `e2_9b_session_1`, reviewed 0/414.)

## 20. What did NOT happen (per explicit instruction)

- D3-v5 was **not** re-scored against this new cohort.
- IMAGE-v2 was **not** run against this new cohort (infrastructure-only check, Section 11).
- COMBINED-IDENTITY-v2 was **not** run against this new cohort.
- No precision/coverage/certification number was calculated for this cohort.
- No certification occurred.
- E3 was not touched. No pricing, Fair Value runtime, or Explorer change was made.
- Nothing was staged, committed, or pushed.

---

## Final result

**`EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_READY_FOR_HUMAN_LABELING`**

A genuinely new, real, policy-blind 414-row cohort (69/70 target cards, 6 rows each where market availability permitted) was captured live from eBay after COMBINED-IDENTITY-v2's freeze, using the durably-preserved E2.8 canonical-resolution manifest (byte-equality proven) and excluding all prior D2/D3/V4/V5/E2.6–E2.9A evidence (9,016 exact-ID + 53 relist-fingerprint exclusions, independently re-verified at 0 leaks in the final cohort). The review session (`e2_9b_session_1`, reviewed_count=0) reuses the corrected V5 review UX verbatim, validated by 99 passing adapted tests plus direct checks against the real queue. No model, image, or policy output exists anywhere in the reviewer-facing data. Human labeling has not begun.
