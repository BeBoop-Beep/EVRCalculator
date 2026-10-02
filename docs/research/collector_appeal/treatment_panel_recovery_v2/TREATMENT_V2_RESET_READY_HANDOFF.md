# Treatment V2 Reset-Ready Handoff

Status: `TREATMENT_V2_RESET_READY`

Date: 2026-10-02

Branch: `research/treatment-panel-recovery-v2-current-20261001`

Draft PR: #529 — `research: build Set-relative Treatment hierarchy with PkmnPrices`

## Current research decision

The supported partial order remains:

**SIR > {Double Rare, Ultra Rare}**

Ultra Rare vs Double Rare remains unresolved as a universal relationship.

Independent replication showed material Set-level Treatment heterogeneity, so the current confirmatory architecture is Set-relative rather than a single universal rarity ladder.

## Frozen V2 target

Fresh expansion:

- 56 triads
- 168 cards
- 10 Sets
- market-date authority: `2026-09-29`
- history period: `180d`
- provider credit cap: `22000`
- production writes: `0`

Target fingerprint:

`28b344ca8ea95ba8fbc9fa947cdb28a1a3d83408482572084ee83e1cf992563d`

Expected by Set:

- Pitch Black: 4
- Destined Rivals: 8
- Surging Sparks: 7
- Black Bolt: 6
- Journey Together: 6
- Scarlet and Violet Base Set: 6
- Temporal Forces: 6
- White Flare: 6
- Shrouded Fable: 4
- Stellar Crown: 3

Cached PkmnPrices identities at latest preflight:

- 23 / 168 cards
- no additional target mappings found in `pkmnprices_ebay_sold_evidence_v1`
- no additional target mappings found in `pkmnprices_sold_sync_state_v1`

The remaining provider identity resolutions are therefore genuine provider work under current local authority.

## Existing independent panel

Frozen prior panel workflow run:

`36971438903`

Artifact:

`treatment-joint-replication-v1-panel`

Ready cohort:

- 20 triads
- 5 Sets

This prior panel remains the only allowed independent prior input to the combined V2 estimator.

## Previous failed capture

Run:

`37061908972`

Outcome:

- provider probe returned `429 credit_limit_exceeded`
- frozen capture did not start
- no valid fresh capture artifact
- no V2 statistical result

This run is not an authorized estimator input.

## Provider reset / budget context

PkmnPrices account daily limit:

- 75,000 credits / UTC day

Authoritative reset boundary:

- `00:00 UTC`
- `17:00 America/Phoenix` for this run

Known scheduled consumers around reset:

- B4: `17:00` Phoenix; currently 207/207 complete and spending 0 provider credits
- Core Panel increment: first retry `17:02`; maximum 8,000 credits/day
- B5: `17:07`; maximum 55,000 credits/day

Treatment V2 must own the shared provider window before Core Panel/B5 can consume the new credit day.

## Hardened capture workflow

Workflow:

`.github/workflows/treatment-set-relative-expansion-v2-capture.yml`

The capture is now:

- `workflow_dispatch` only
- self-hosted VM runner
- refuses provider spend before UTC credit day `2026-10-03`
- honors `/home/ubuntu/state/db-safety/hold.json`
- re-verifies the exact frozen 56-triad fingerprint before provider calls
- acquires `/tmp/active-supply-panel.lock`
- checks `/tmp/pokemon-scrape-dispatcher.lock`
- acquires `/tmp/pkmnprices-api.lock`
- checks/holds `/tmp/pokemon-post-scrape-publication.lock`
- uses the frozen 22,000-credit cap
- uploads preflight + capture artifacts
- automatically chains a successful capture into the Set-relative V2 estimator

No standalone provider probe is performed before capture.

## Estimator path

Normal path:

A successful capture job automatically launches the `estimate` job in the same workflow run.

Fresh artifact:

`treatment-set-relative-expansion-v2-capture`

Prior artifact:

`treatment-joint-replication-v1-panel` from run `36971438903`

Output artifact:

`treatment-set-relative-hierarchy-v2`

Fallback estimator workflow:

`.github/workflows/treatment-set-relative-hierarchy-v2.yml`

The fallback requires an explicit `capture_run_id` and validates:

- selected run completed
- selected run conclusion is success
- selected branch is the frozen research branch
- selected workflow is the Treatment V2 capture workflow

The stale failed run `37061908972` is not hard-coded anywhere in the current capture/estimator path.

## Frozen V2 coverage gate

Proceed to Set-relative fitting only if:

- >=45 / 56 fresh triads ready
- Pitch Black >=3 ready triads
- >=7 of 9 fresh Scarlet & Violet Sets have >=3 ready triads
- >=120 / 168 fresh cards return usable history
- production writes = 0

If coverage fails:

`SET_RELATIVE_TREATMENT_V2_INSUFFICIENT_EXPANSION_COVERAGE`

If coverage passes and all statistical gates pass:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION`

If coverage passes but statistical gates fail:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED`

## Zero-provider validation

Latest validation workflow:

`37074707700`

Result:

- SUCCESS
- 8 tests passed
- workflow YAML parsed
- every Bash `run:` block syntax-checked
- provider-isolation guards passed
- hierarchy estimator unit tests passed
- live DB preflight returned `PREFLIGHT_OK`
- production writes = 0
- no PkmnPrices calls

Latest preflight artifact:

`11256300423`

## Conditional normalization preregistration

Frozen document:

`docs/research/collector_appeal/treatment_panel_recovery_v2/TREATMENT_APPEAL_NORMALIZATION_V1_PREREGISTRATION.md`

It may run only if V2 returns:

`SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION`

Important frozen boundaries:

- Collector V7 remains the unchanged price-blind control
- Treatment challenger is market-calibrated offline, price-independent at scoring time
- challenger may not reuse the V7 model version/fingerprint
- scarcity/Artist/Playability nuisance coefficients are not re-added at scoring time
- Fair Value may not evaluate on price observations used to fit Treatment
- global fallback is disabled by default
- unsupported Treatment families remain unavailable
- Double Rare is normalized to Treatment Appeal 50
- future Collector shadow uses a signed bounded headroom transform
- Treatment weight is not selected yet

## Next action after provider reset

After the UTC credit day has reset, dispatch:

**Treatment Set-Relative Expansion V2 Capture**

on:

`research/treatment-panel-recovery-v2-current-20261001`

Do not rerun the old failed capture.

Do not change the cohort, target fingerprint, credit cap, normalization rule, or statistical gates before observing the frozen V2 outcome.

## Production boundary

Research only.

- canonical pricing mutation: NONE
- Collector Appeal mutation: NONE
- Overall RIP mutation: NONE
- Rankings mutation: NONE
- Set-page publication: NONE
