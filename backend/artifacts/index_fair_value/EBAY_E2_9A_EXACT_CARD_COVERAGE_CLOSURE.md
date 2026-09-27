# EBAY_E2_9A — Exact Card-Coverage Closure

**Status:** `EBAY_COMBINED_IDENTITY_V2_ALL_HISTORICAL_GATES_PASS_NEW_BLIND_CAPTURE_JUSTIFIED`

**Worktree:** `D:\EVRCalculator-ebay-e2.9`, branch `feature/ebay-e2.9-image-veto-tiered-identity`, HEAD `aee7f131`. All work below is uncommitted. Nothing was staged, committed, or pushed by this task.

**COMBINED-IDENTITY-v2 was NOT changed.** `backend/scripts/ebay_combined_identity_policy_v2.py`'s source hash still matches the frozen `ebay_combined_identity_v2_freeze_manifest.json` (`policy_source_sha256 = 59e32c0a8a0310bf9a27417a78d566942f303cb543c4e3165f1ead39954abf07`), locked by `test_combined_identity_v2_policy_source_hash_matches_frozen_manifest`. D3-v5, IMAGE-v2, Tier A, Tier B, and all certification gate thresholds were not modified. This task only resolved the previously unmeasured **exact card-coverage** gate that EBAY_E2_9 left as `UNMEASURED` (bounded 0.686–0.814 for V4, 0.629–0.829 for V5).

---

## 1. What changed since EBAY_E2_9

EBAY_E2_9's report (`EBAY_E2_9_IMAGE_VETO_TIERED_IDENTITY_POLICY.md`, Section 9) stated the canonical-image resolution manifest that produced E2.8's frozen per-row image states "lived in a prior session's temp scratch directory and no longer exists." That claim was re-checked at the start of this task and found **incorrect**: the manifest and its 134 resolved canonical card images are still present on disk at

```
C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e28_canonical_targets\resolve_manifest.json
```

and the exact runner that consumes it — `backend/scripts/run_ebay_combined_identity_historical_diagnostic.py` (E2.8's own script, already committed-in-worktree via this branch's untracked file set, unmodified) — hard-codes this same path as `RESOLVE_MANIFEST_PATH` and exposes `build_gallery_from_resolution()`. This is the real E2.8 image execution path; it was located and reused exactly, not reimplemented.

## 2. Scoped rows

Per instructions, only rows capable of contributing a new eligible accept under COMBINED-IDENTITY-v2 were processed for image state: `D3-v5 text_state == HIGH_CONFIDENCE` AND no existing text contradiction (`ebay_combined_identity_policy_v1.has_text_contradiction`, frozen).

| Cohort | Scoped rows |
|---|---|
| V4 | 216 |
| V5 | 222 (221 human-YES + 1 human-UNCERTAIN, carried through for completeness, excluded from all precision/coverage accounting) |
| **Total** | **438** |

This matches the ~437 estimate. Every excluded row (REJECTED / MEDIUM_CONFIDENCE / AMBIGUOUS text, or a HIGH_CONFIDENCE row a text contradiction already vetoes) cannot reach Tier A or Tier B under v2's own decision table, so it cannot change the coverage answer and was not image-processed.

## 3. New execution artifact

`backend/scripts/run_ebay_e2_9a_exact_card_coverage.py` (new, measurement-only, non-certifying). Reuses, without modification:

- `ebay_d3_matcher_v5.classify_listing` (frozen text authority)
- `ebay_combined_identity_policy_v1.has_text_contradiction` / `resolve_image_state` (frozen; the latter wraps frozen IMAGE-v2 `verify_by_retrieval`)
- `run_ebay_combined_identity_historical_diagnostic.build_gallery_from_resolution` / `_load_rows` / `_target_dict` / `_listing_dict` / `classify_human_label` (E2.8's real execution path, imported, not copied)
- `ebay_combined_identity_policy_v2.combine` (frozen v2 policy under evaluation)

Outputs:
- `backend/artifacts/index_fair_value/ebay_e2_9a_exact_card_coverage_per_row.json` — full per-row results for all 438 scoped rows.
- `backend/artifacts/index_fair_value/ebay_e2_9a_exact_card_coverage_summary.json` — reproduction check, exact coverage, and four-gate evaluation.

Real network fetches (real eBay listing photos, real Pokemon TCG API canonical images already resolved) and a real DINOv2-small forward pass were performed for every scoped row — no synthetic or invented image data.

Canonical gallery coverage: **70/70 target cards present (100%)** — `missing_target_identities: []`. No `UNVERIFIED_TARGET_NOT_IN_GALLERY` rows occurred.

## 4. Reproduction check — REQUIRED gate, PASSED

Recomputing the 438 scoped rows independently reproduces the already-frozen E2.8/E2.9 aggregate exactly:

| Metric | V4 observed | V4 frozen | V5 observed | V5 frozen |
|---|---|---|---|---|
| Tier A (MATCH) accepted | 115 | 115 | 107 | 107 |
| Tier B (UNVERIFIED) accepted | 88 | 88 | 99 | 99 |
| MISMATCH + human-YES | 13 | 13 | 15 | 15 |
| Combined true accepts | 203 | 203 | 206 | 206 |
| Combined false accepts | 0 | 0 | 0 | 0 |
| Combined precision | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Combined Wilson lower (95%) | 0.981428 | 0.9814 | 0.981694 | 0.9817 |
| Catastrophic false accepts | 0 | 0 | 0 | 0 |
| HIGH_CONFIDENCE + UNVERIFIED + human-NO | 0 | 0 | 0 | 0 |

**`_all_reproduced: true`** for both cohorts (`ebay_e2_9a_exact_card_coverage_summary.json` → `reproduction_check`). The rerun is a fully consistent extension of the same frozen historical evidence, not a divergent recomputation — this pass did not proceed to publish a coverage number on a non-equivalent rerun.

## 5. Exact card coverage

Target universe: **70 cards**, identical population for both V4 and V5 (confirmed by the gallery-resolution step: only 70 distinct `canonical_card_id`s are requested across both cohorts combined).

| | V4 | V5 |
|---|---|---|
| A. Total target cards | 70 | 70 |
| B. Cards with ≥1 true Tier A accept | 48 | 44 |
| C. Cards with no Tier A but ≥1 true Tier B accept | 8 | 12 |
| D. Total covered (Tier A OR Tier B, no double-count) | 56 | 56 |
| E. Exact coverage (D / 70) | **0.8000** | **0.8000** |

No card in either cohort carries both a Tier A and a Tier B true accept counted twice — verified by `test_card_with_both_tier_a_and_tier_b_is_not_double_counted` and by construction (`tier_b_only_cards = tier_b_cards - tier_a_cards`).

### V4 — Tier A covered (48 cards)
`0331d96e-d8af-44d3-9552-85f784d9b4ca`, `0b81872e-b089-49e9-aec3-16a535b12efb`, `0dde3317-5162-49d1-b5c9-6b206a086d2c`, `10a47631-ea19-4b62-8a93-4b1b3e6b3013`, `152906c9-3b9f-4f16-bb22-cb4241c7386b`, `15faf94c-4a3b-4f09-a867-f2ded1174419`, `209f02db-d953-4dde-bbd6-0822671fe1d1`, `21e9ddc5-2751-4886-9e08-a1c6e2cc14e4`, `23d6bd35-bbf0-49b2-911e-4949e66ff8bb`, `2cef0dfb-a5fd-4aed-b8ae-34a82f414587`, `2e5780f8-1769-4d26-9e3e-87e4a27d4dfe`, `301185dd-2bde-4699-80bd-8b2a3cfd8f7f`, `31566cbb-0eeb-499e-aa6d-b9b0bd85fc8b`, `33dca102-b449-4da6-bfa6-7b72de711596`, `3755e7ef-e482-4186-8377-e717f80b3759`, `3b5294d0-4738-4296-952e-f32b2788e3c4`, `53466d2d-94fd-4230-9505-694297a9030d`, `5576e4b9-4873-40fa-84c4-da9f28cec096`, `605a2c1a-6a14-463e-b1e2-b55cd9c16244`, `64c0404b-826f-493d-9c10-738b2b56eca4`, `67611b34-a7e9-497f-9708-651cc015ca6c`, `6a1e2c02-b24d-4001-96f1-8bc2a24d8ccd`, `6a2b87e5-f90b-48f4-be30-a77258bee660`, `6a980108-6683-4461-ac9a-c81a27326dee`, `75720435-3807-46b6-b3da-5e1c53b77822`, `77b44a76-26f7-4fa0-a548-c29870a7bb68`, `7f065a2b-5cab-45c8-8fd8-96d4c07c4ee8`, `828c0d0d-2ede-4bab-bed4-407cd3cf8662`, `829b12ba-c7f5-4796-9a57-a2a2463c8461`, `966bcb61-bf43-4cd7-8287-42f4bb9fa76d`, `97165c7e-1d85-4962-807e-5661c2115d7d`, `a3d56338-1f3f-4b99-8920-5d71b8b85737`, `a6969678-b361-4b27-bee3-e3cdc127a5e4`, `a922341e-4646-470b-95cf-2a59055b18ce`, `ae4a6acb-3a88-4547-a165-7a617bfb2ce8`, `b3020b76-9ff0-449a-85b8-924878fa0e8b`, `b547c5c3-7082-4a7f-9290-3d569b91b462`, `b620ec1c-c0ac-4e7e-919d-a7df98bcb84b`, `b801a524-e703-4f4c-ad99-1ec742cf30ec`, `bf928dd7-24bc-4e16-bb5e-afb8122c3241`, `c7e36a14-236f-4b93-a4a8-a4be2ddc7193`, `cc59d868-d0e5-4557-9423-3f9b7c9d2591`, `d09b2fb5-41b6-4d1e-88cf-629402434501`, `d12a209b-06a3-4b46-82d3-a374e6bbe7b4`, `d4ff3ebb-7e40-4a36-88e6-f07af2977641`, `e26de7b7-434e-4bec-8fc2-fb15b971b1a7`, `f01e01fe-17e4-48b7-8ba3-9a88f876acd4`, `fd225f1d-3765-4209-a5ec-42caf35933b0`

### V4 — Tier B incremental recovery (8 cards)
`018c983e-b1d0-41df-880e-ebf3f2e2fb12`, `147a436d-4ccc-43d1-b19a-20b74d2ff723`, `2c445258-b198-43de-b710-0921ebe3f0ab`, `4206e794-1ec6-4d55-94d4-63267ac9a183`, `4299cd6b-98e3-4e65-865f-26a39b19fe5b`, `640cd931-d97f-4173-ad9d-3ab86f91d92c`, `7b00ea04-5c2a-4172-8025-afba48ddacb3`, `9f323989-e972-4a9e-9e7b-3166e85d0690`

### V4 — Still uncovered (1 card)
`3baf2f12-759f-427a-b8d0-2511e639310f`

### V5 — Tier A covered (44 cards)
`018c983e-b1d0-41df-880e-ebf3f2e2fb12`, `0b81872e-b089-49e9-aec3-16a535b12efb`, `0dde3317-5162-49d1-b5c9-6b206a086d2c`, `10a47631-ea19-4b62-8a93-4b1b3e6b3013`, `147a436d-4ccc-43d1-b19a-20b74d2ff723`, `15faf94c-4a3b-4f09-a867-f2ded1174419`, `21e9ddc5-2751-4886-9e08-a1c6e2cc14e4`, `23d6bd35-bbf0-49b2-911e-4949e66ff8bb`, `25638dbd-2434-4a4f-ba0d-dcf3e3e114ca`, `2cef0dfb-a5fd-4aed-b8ae-34a82f414587`, `2e5780f8-1769-4d26-9e3e-87e4a27d4dfe`, `33dca102-b449-4da6-bfa6-7b72de711596`, `3755e7ef-e482-4186-8377-e717f80b3759`, `3b5294d0-4738-4296-952e-f32b2788e3c4`, `4206e794-1ec6-4d55-94d4-63267ac9a183`, `4299cd6b-98e3-4e65-865f-26a39b19fe5b`, `5576e4b9-4873-40fa-84c4-da9f28cec096`, `605a2c1a-6a14-463e-b1e2-b55cd9c16244`, `64c0404b-826f-493d-9c10-738b2b56eca4`, `67611b34-a7e9-497f-9708-651cc015ca6c`, `6a1e2c02-b24d-4001-96f1-8bc2a24d8ccd`, `6a2b87e5-f90b-48f4-be30-a77258bee660`, `6a980108-6683-4461-ac9a-c81a27326dee`, `75720435-3807-46b6-b3da-5e1c53b77822`, `7b00ea04-5c2a-4172-8025-afba48ddacb3`, `7f065a2b-5cab-45c8-8fd8-96d4c07c4ee8`, `828c0d0d-2ede-4bab-bed4-407cd3cf8662`, `829b12ba-c7f5-4796-9a57-a2a2463c8461`, `966bcb61-bf43-4cd7-8287-42f4bb9fa76d`, `97165c7e-1d85-4962-807e-5661c2115d7d`, `9f323989-e972-4a9e-9e7b-3166e85d0690`, `a6969678-b361-4b27-bee3-e3cdc127a5e4`, `ae4a6acb-3a88-4547-a165-7a617bfb2ce8`, `b547c5c3-7082-4a7f-9290-3d569b91b462`, `b620ec1c-c0ac-4e7e-919d-a7df98bcb84b`, `bf928dd7-24bc-4e16-bb5e-afb8122c3241`, `c7e36a14-236f-4b93-a4a8-a4be2ddc7193`, `cc59d868-d0e5-4557-9423-3f9b7c9d2591`, `d09b2fb5-41b6-4d1e-88cf-629402434501`, `d12a209b-06a3-4b46-82d3-a374e6bbe7b4`, `d4ff3ebb-7e40-4a36-88e6-f07af2977641`, `e26de7b7-434e-4bec-8fc2-fb15b971b1a7`, `f01e01fe-17e4-48b7-8ba3-9a88f876acd4`, `fd225f1d-3765-4209-a5ec-42caf35933b0`

### V5 — Tier B incremental recovery (12 cards)
`0331d96e-d8af-44d3-9552-85f784d9b4ca`, `152906c9-3b9f-4f16-bb22-cb4241c7386b`, `209f02db-d953-4dde-bbd6-0822671fe1d1`, `301185dd-2bde-4699-80bd-8b2a3cfd8f7f`, `31566cbb-0eeb-499e-aa6d-b9b0bd85fc8b`, `3c75f577-62ee-4bdf-865c-ab2384f4379b`, `53466d2d-94fd-4230-9505-694297a9030d`, `77b44a76-26f7-4fa0-a548-c29870a7bb68`, `a3d56338-1f3f-4b99-8920-5d71b8b85737`, `a922341e-4646-470b-95cf-2a59055b18ce`, `b3020b76-9ff0-449a-85b8-924878fa0e8b`, `b801a524-e703-4f4c-ad99-1ec742cf30ec`

### V5 — Still uncovered (2 cards)
`2c445258-b198-43de-b710-0921ebe3f0ab`, `3baf2f12-759f-427a-b8d0-2511e639310f`

(Card `3baf2f12-759f-427a-b8d0-2511e639310f` is uncovered in **both** cohorts.)

## 6. Four final historical gates

| Gate | Threshold | V4 | V5 | Result |
|---|---|---|---|---|
| Accepted precision | ≥ 0.99 | 1.0000 | 1.0000 | **PASS** (both) |
| Wilson lower (95%) | ≥ 0.98 | 0.9814 | 0.9817 | **PASS** (both) |
| Card coverage | ≥ 0.80 | 0.8000 | 0.8000 | **PASS** (both) |
| Catastrophic false accepts | == 0 | 0 | 0 | **PASS** (both) |

Both cohorts pass all four gates. Coverage lands exactly on the 0.80 boundary in both cohorts (56/70) — a real, measured tie, not a rounding artifact (56/70 = 0.8 exactly; `test_four_gates_boundary_is_inclusive` locks in that `>= 0.80` accepts this value rather than silently requiring strictly-greater).

## 7. Frozen-policy fingerprint (unchanged)

| Field | Value |
|---|---|
| policy_source_sha256 | `59e32c0a8a0310bf9a27417a78d566942f303cb543c4e3165f1ead39954abf07` |
| policy_fingerprint | `7105b731d40b121d5e74089a92c065bfc8b86795281262d275192bf6049c1018` |
| text_matcher_fingerprint | `93301e5da1cf8129896993f12cfec2b66c5c887d679cb6f0755785c884581c69` |
| image_verifier_fingerprint | `bf50ee1fb1160711e9591755ee4905e7e4884946f7f079adeac0bb184c680ea1` |
| certified_against_new_blind | `false` (unchanged — this task did not certify anything) |

Confirmed unchanged by `test_combined_identity_v2_policy_source_hash_matches_frozen_manifest`, `test_combined_identity_v2_eligible_states_unchanged`, and `test_combined_identity_v2_still_not_certified_against_a_new_blind`.

## 8. Tests

`backend/tests/unit/scripts/test_ebay_e2_9a_exact_card_coverage.py` — 18 new tests, all passing:

- Exact distinct-card coverage arithmetic (`D / 70`)
- Tier A/Tier B de-duplication (a card with both never double-counts)
- Tier B incremental recovery (a card with no Tier A accept but a Tier B accept counts once)
- A false-accept row never contributes to coverage
- Uncovered-card reporting by id
- Scoping predicate (`HIGH_CONFIDENCE` + no contradiction only)
- Four-gate evaluation, including a boundary-inclusivity test for the exact 0.80 tie this run produced
- Reproduction-check accounting against the frozen E2.8/E2.9 expected counts, including the central HIGH_CONFIDENCE+UNVERIFIED+human-NO catastrophic-signal check
- Frozen fingerprint / manifest immutability

```
python -m pytest backend/tests/unit/scripts/test_ebay_e2_9a_exact_card_coverage.py -q
18 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
499 passed, 1 failed (pre-existing, unrelated CRLF byte-hash checkout artifact:
test_ebay_d2v_validation.py::test_exact_frozen_matcher_and_config_are_unchanged;
confirmed via `git diff --quiet HEAD -- backend/scripts/ebay_d2m_matcher.py`
that the file is byte-identical to HEAD -- same pre-existing issue documented
in EBAY_E2_9 Section 13, reproduces unchanged against HEAD, out of scope here)
```

## 9. Fair Value / Explorer blocker status

**Fair Value: UNBLOCKED for the identity-evidence gate.** All four COMBINED-IDENTITY-v2 historical gates now pass on both consumed cohorts. E3 (source-estimate/price-weighting logic) may proceed to the next phase, which — per the task's own decision gate — is capturing a fresh blind cohort to certify COMBINED-IDENTITY-v2 out-of-sample (not performed in this task; see Stop Condition).

---

## Final result

**`EBAY_COMBINED_IDENTITY_V2_ALL_HISTORICAL_GATES_PASS_NEW_BLIND_CAPTURE_JUSTIFIED`**
