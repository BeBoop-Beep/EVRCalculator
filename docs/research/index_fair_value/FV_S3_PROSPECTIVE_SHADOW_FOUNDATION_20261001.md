# FV-S3 — Prospective shadow foundation

**Status: `FV_PROSPECTIVE_SHADOW_FOUNDATION_READY_PROVIDER_CANARY_BLOCKED`**

Research only. Nothing here changes a canonical price, Set Value, Market Explorer, Rankings/RIP, Collector Appeal or
any public Fair Value. The FV-S2 rule (`EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1`) is frozen and unchanged; its module
hash is pinned by a test and by the preregistration. No provider call, credential load, production write, VM action,
scheduler activation, push, PR, merge or deployment occurred. The daily collector and the canary are both disabled.

## 0. Rebase onto current develop

Branch rebased onto `origin/develop` = `07d88bdf` (re-checked with `ls-remote` at execution; still the tip) with no
conflicts. FV-S2 artifacts regenerate **byte-identical** to the committed blobs after the rebase; 190 scoped tests pass
(184 earlier + 6 newer B5 tests). The one failing test (`test_broad_pilot_workflow_persists_without_extra_collection_step`)
fails identically on current develop: the workflow at `07d88bdf` contains no `--persist-evidence`.

Develop changes that mattered:
* **B5 exact-target-variant scope (`B5_SCOPE_VERSION = exact_target_variant_v2`)**: B5 now writes `b5_*` keys into the
  sync-state metadata (`_persist_scope_reconciliation`). The increment collector passes the whole sync row through and
  adds only its own namespaced key, so the two coexist; a test asserts every pre-existing field/key (including a
  `core_panel_backfill_cursor`) is unchanged.
* No change to any provider credit cap, wrapper, lock order or schedule (B4/B5/C wrappers and crontabs unchanged;
  the other 200+ commits are Market Explorer/Rankings/Collector/Sentinel).

## 1. Shadow ledger contract

Audit: no existing table fits (price-storage-v2 shadow, RIP benchmark, active-supply and EV-representativeness tables
are domain-specific, none is a generic append-only publication ledger). A new ledger is **prepared, not applied**, at
`fv_s3/migration_proposal_unapplied/20261001000000_fair_value_shadow_ledger_v1.sql.proposed` (extension and location
chosen so no migration runner can pick it up; a test asserts it is in neither migration directory).

| Part | Table | Written | Content |
| --- | --- | --- | --- |
| A | `fair_value_shadow_anchor_publications_v1` + `…_anchor_members_v1` | before any comparison price is read | every field in the request (IDs, rule version, evaluation date, information/evidence cutoff, window, comp count, sold-date min/max, collected/ingested max, median, Q1/Q3/IQR/MAD, distinct days, membership + evidence fingerprints, exact eligible members, exclusion counts, evidence status, input fingerprints, generated_at, source commit) |
| B | `…_component_observations_v1` | after A | market, structural baseline, scarcity, Collector Appeal, comp count, window, dispersion, evidence age, three divergences, shadow status; `blended_value` is CHECKed NULL |
| C | `…_evaluation_outcomes_v1` | per horizon 0/1/7/30 | comparison date/price, abs + pct error, forward market change; a trigger forces `comparison_date = evaluation_date + horizon` and `anchor = published median` |

Guarantees (Python reference implementation + DDL, both tested):
* **Append-only**: no update/delete path; DB triggers raise on UPDATE/DELETE/TRUNCATE; service role gets SELECT, INSERT only.
* **Idempotent retry**: key = (rule_version, card, evaluation_date, information_cutoff). Same `content_fingerprint`
  (which excludes `generated_at` and `source_commit`) → no-op, first row wins; different content → hard conflict, never an overwrite.
* **Information availability**: a transaction is a member only if `collected_at <= cutoff` **and** (when stamped)
  provider `ingested_at <= cutoff` **and** `sold_at <= evaluation_date`; missing/unparseable timestamps fail closed.
  `sold_at` alone never qualifies (test: 12 old sales collected after the cutoff → publication has zero members). The DDL
  repeats the gate in a trigger on members and in CHECKs on the publication.
* **Evidence status** is one of `PROSPECTIVE_AS_KNOWN_AT_CUTOFF`, `AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE`,
  `RETROSPECTIVE_BACKFILLED_EVIDENCE`; a prospective row must be generated at/after its cutoff.
* **Comparison-price boundary**: the anchor builder has no price/market/comparison/target/outcome parameter, refuses any
  evidence row or fingerprint carrying such a key (`SHADOW_ANCHOR_COMPARISON_LEAKAGE_GUARD`), cannot import the
  evaluation/ledger modules (AST test), and the anchor table has no comparison-price column. Evaluation functions
  deep-copy the publication, accept a read-only mapping, return new records, and a test shows ledger publications are
  byte-identical after outcomes at three horizons.
* Insufficient-comp cards are **recorded** (`INSUFFICIENT_COMPS`), so absence is data too.
* A database adapter exists but is dormant (`WRITE_ENABLED = False`, refuses before any call).

Components stay separate and never blend: market, anchor, structural, scarcity, appeal, and
`anchor − market`, `structural − market`, `anchor − structural` (USD and % of reference). Frozen sources for the
non-anchor components are labelled (`F2_MODELC_OOF_FROZEN_RESEARCH_COMPARATOR`, `F1_DATASET_FROZEN`); scarcity and
Collector Appeal are not rewritten.

## 2. Preregistration (`fv_s3/preregistration_v1.json`)

Frozen with the module hash `f0beb161…c0af5a`, the methodology-contract hash and the panel fingerprint, with
`first_prospective_publication_exists_at_freeze = false`. A test fails if the rule module changes without a new version
or if the artifact drifts from the in-code contract.

* **Anchor accuracy** at the publication date: MdAPE, MAE, dollar R², Spearman, within 10/20/30% — for all anchored
  cards, ≥ $25, ≥ $100, ≥ $250; coverage reported separately; < 30 cards labelled `INSUFFICIENT_N`.
* **Forward behaviour** at +1/+7/+30 days, diagnostic only, convergence not required, no conclusion chosen:
  divergence `d = (anchor − market₀)/market₀` vs forward return — Spearman, sign agreement for |d| ≥ 5%, OLS slope with
  set-clustered bootstrap CI (B = 2000, seed 20261001), mean return by divergence tercile, and a predictor test (is the
  anchor closer to the future price than today's market price?). Both readings (informative divergence vs contemporaneous
  alternative estimator) are stated as live possibilities. Missing outcomes are never imputed; all horizons × strata are
  reported (no selection after the fact).
* Observing results never edits V1; a change creates `ANCHOR_V2` and restarts the clock.

All metrics are implemented and unit-tested (known-value, formula, determinism, small-N).

### Finding: no true as-known history exists before 2026-09-30

All 59,050 evidence rows were collected between `2026-09-29T22:06Z` and `2026-09-30T15:22Z`. An as-known replay of the
anchor is therefore empty (0/207 anchored) for every evaluation date up to 09-28 and reproduces the retrospective
194/207 only at cutoff 2026-10-01 00:00Z (artifact `shadow_s3/as_known_replay_20260930.json`, labelled
`RETROSPECTIVE_AS_KNOWN_REPLAY_NOT_A_PUBLICATION`; replay MdAPE 9.68% / ≥ $100 6.27% / ≥ $250 7.15% on n = 25, same as FV-S2).
The first honest prospective observation can only start after the daily collector runs.

## 3. Catch-up debt planner (`plan_core_panel_catchup.py`, live read-only run)

631 SELECTs, 0 provider calls, 0 writes; intended activation `2026-10-08` (re-run with the real date).

| | |
| --- | --- |
| Cards | 207 (all have cached identity, `phase1_ready`, and a B4 watermark frontier) |
| B4 completion | 186 `HORIZON_180D` (lifetime cursor still PARTIAL), 21 `PROVIDER_DRAINED` |
| Frontier span | 2026-09-03 … 2026-09-30 (watermarks were set as each card's backfill began) |
| Catch-up interval | 7.9 – 34.7 days, median 13.9 |
| States | **170 POTENTIAL_OVERFLOW**, **37 NEEDS_CANARY_SEMANTICS**, 0 BLOCKED, **0 READY** (unreachable until the canary) |
| Days to clear at 4 pages/card/day | 1 day: 131 cards · 2: 51 · 3: 14 · 4: 7 · 5: 4 |
| First-day credit demand | 12,360 uncapped vs 8,000 cap → multi-day catch-up |

Method: rows ingested in the 30 days before the frontier ÷ 30 × interval, doubled as a safety factor. A card is
POTENTIAL_OVERFLOW if that exceeds one 20-row page. It is a planner, not an assertion that the gap is recoverable
(`since` semantics unverified).

**Defect found and fixed by the planner:** the FV-S2 collector required a fully drained lifetime backfill and would have
blocked 186 of 207 cards. B4 only walks to a 180-day horizon. Eligibility is now identity + `phase1_ready` + recorded
frontier; the lifetime cursor is never read or modified (new test with a PARTIAL card and a sentinel cursor).

## 4. Disabled one-card provider canary (`run_core_panel_provider_semantics_canary.py`)

`CANARY_ENABLED = False`; `--commit` exits 78 before reading the plan, loading credentials or touching anything
(test proves the plan file is not even read). Hard bounds: one provider card, one page, `limit = 20`, **≤ 20 credits**,
no identity lookup, no cursor, `graded=None`, `sort=date_desc`, `since=<frontier>`, **no database write** (a local
receipt only; the activation-time DB handle is the select-only wrapper). Not schedulable: no wrapper, cron or workflow;
requires an interactive TTY, an authorization ticket `FVCANARY-YYYYMMDD-ID`, that the requested card equals the
deterministic selection recomputed from the plan, DB-safety hold checked before and after the locks, and the same lock
order as B5 (tested). It checks all eight requested semantics and classifies billing (per item / per limit / flat /
ambiguous full page / other); its verdict never flips `SINCE_SEMANTICS_VERIFIED` by itself.

Selection is a rule, not a name: eligible cards with ≥ 10 estimated new rows, closest estimate to one full page, ties by
canonical id. Current plan selects **Terapagos ex 169 (Prismatic Evolutions)**, provider card 16114, frontier
`2026-09-25T02:22:24Z`, ≈ 20.6 estimated rows, 170 candidates. Umbreon is not hardcoded.

Future operator command (only after a reviewed change sets `CANARY_ENABLED = True`, a release pin, and approval; run
interactively on the VM with a plan regenerated at that time):

```
python -m backend.scripts.run_core_panel_provider_semantics_canary --commit \
  --plan backend/artifacts/index_fair_value/shadow_s3/catchup_debt_plan.json \
  --canonical-card-id 280d4345-82c1-4af1-b54f-35fe0399a979 \
  --authorization-ticket FVCANARY-<YYYYMMDD>-<ID> \
  --receipt-out /home/ubuntu/state/core_panel_canary/receipt.json
```

Hard credit ceiling: **20 credits, once**.

## 5. Daily credit budget, re-derived from current source

| Consumer | Daily cap | Source on `07d88bdf` |
| --- | ---: | --- |
| Account ceiling (UTC day) | 75,000 | `ACCOUNT_DAILY_CREDIT_LIMIT` (B5) |
| B5 | 55,000 | `DAILY_B5_CREDIT_CAP` |
| Active supply C | 4,500 | `FULL_PANEL_CREDIT_CAP` (projected 4,140) |
| Vintage-gap daily | 600 | workflow `--item-credit-cap 600` (the only *scheduled* GitHub PkmnPrices job; the other workflows are `workflow_dispatch`-only: 30 / 300 / backfill / pilot 4,500) |
| B4 | 55,000 informational | cron `*/15`, but **inert**: 207/207 cards are `phase1_ready` (planner) |
| **Core Panel increment** | **8,000** | 4,140 mandatory page pass + 3,860 bounded overflow |
| Canary | 20, once | not daily |
| **Committed** | **68,100** | **6,900 unallocated** (≥ 5,000 required, asserted at import) |

Result: **unchanged from the earlier derivation**; none of the 214 intervening commits touched a cap, wrapper or schedule.
New protections: (a) a test scans every workflow and live VM crontab and fails if a scheduled PkmnPrices consumer
appears that is not in the audited set; (b) a test pins the current source constants; (c) the runtime budget subtracts
today's spend by every *other* sold-run mode and the full active-supply cap, so if B4/B5 (or anything) has overspent, the
collector's room shrinks to zero and it yields; (d) a provider `x-credits-limit` other than 75,000 halts the run.
(The multi-source eBay pricing cron uses the eBay API, not PkmnPrices credits.)

## 6. Metadata-drift policy for the shadow phase

`FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY` is stamped on every publication (DDL-enforced). The evidence store is not
rewritten; drift is surfaced through the increment collector's per-card receipts and run metadata, and each member keeps
`grader_at_first_seen` / `graded_at_first_seen`. Title rules fail closed on grade contamination. No public or production
surface consumes the rows. A future versioned overlay is designed in `fv_s3/ENRICHMENT_OVERLAY_DESIGN_NOTE.md` and is a
**precondition for any production Fair Value promotion**.

## 7. Remaining blockers

1. **Provider canary** — `since`/`date_desc`/billing semantics unverified; needs explicit operator approval, a reviewed
   enable, and a VM run. Until then no catch-up is asserted recoverable.
2. **Daily collector activation** — disabled; also needs release pin and scheduler install; catch-up debt is multi-day
   (≤ 5 days at the page cap, 12,360 credits uncapped on the first day).
3. **Ledger migration** — proposal unapplied; the first prospective publication needs it (or an approved alternative).
4. **A publisher job** to run the anchor builder daily against live evidence and the canonical comparison feed — the
   pure builder, ledger interface and metrics exist; the scheduled glue does not.
5. **Live structural baseline** — the comparator is the frozen F2 ModelC out-of-fold output; a daily structural value for
   the shadow needs an explicit decision (freeze coefficients vs refresh), without refitting here.
6. **No as-known history before 2026-09-30**, so forward statistics begin only after activation and need ≥ 30 anchored
   cards per horizon before any inference.
7. Enrichment overlay before production use.
