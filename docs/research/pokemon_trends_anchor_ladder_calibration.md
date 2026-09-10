# Pokémon Google Trends Anchor-Ladder Calibration

Status: architecture designed, empirically validated on a live sample, implemented as shadow code with tests. **Full 1,025-Pokémon corrected capture not run.** No new Trends source rows persisted, no snapshot pointer changed, no Collector model touched.

## Phase 1 — Pipeline trace (summary; full trace in agent transcript)

- Batching: `build_anchor_batches()` (`backend/desirability/google_trends.py:401-425`), batch size 5 (1 anchor + 4 targets), anchor is always `"Pikachu"` (`DEFAULT_ANCHOR_TERM`, line 18), targets are sequential windows over the Pokédex-number-sorted universe — no tiering.
- pytrends call: `cat=0, gprop=""` (web search), `geo="US"` default, one of 4 timeframes (`today 1-m/3-m/12-m/5-y`).
- `relative_to_anchor = raw_interest_value / anchor_interest_value` (`google_trends.py:602-604`), only when both are non-null and anchor>0.
- Normalization (`trends_normalization.py:43`): `100*log1p(relative)/log1p(max_relative)`, `max_relative` computed **per call**, not globally.
- Missing/failed requests correctly produce `None`/status=`failed`/`insufficient_data` — never coerced to 0 (verified in code, not a bug in that path).
- `TREND_SCORING_VERSION = "pokemon_google_trends_relative_interest_v1"` (`trends_normalization.py:7`), pluggable at the `composite.build_composite_scores(scoring_version=...)` call site but currently a hardcoded module constant inside `trends_normalization.py`.

## Phase 2 — Empirical reproduction (live pytrends calls, 4 requests, `today 1-m`, `geo=US`)

| Query | Result |
|---|---|
| **A.** Pikachu + Torkoal, Girafarig, Stunky, Purugly (current design) | Pikachu=26.66, Torkoal=0.03, Girafarig=0.03, **Stunky=0.0, Purugly=0.0** |
| **B.** Torkoal, Girafarig, Stunky, Purugly (no Pikachu) | Torkoal=60.28, Girafarig=30.34, **Stunky=17.09, Purugly=7.69** — all clearly non-zero, correctly ordered |
| **C.** Pikachu + Torkoal alone (2-term, no batch dilution) | Pikachu=26.66, **Torkoal=0.03** |

Query C is the decisive result: even with *zero* batch dilution (just the two terms), Torkoal still collapses to near-zero against Pikachu. This proves the defect is a **magnitude-mismatch resolution artifact**, not a batch-size artifact — ruling out "just use smaller batches" and confirming that any design pairing a weak-to-mid-tier Pokémon directly against a global superstar anchor will fail, regardless of batch size. This is direct evidence *for* the anchor-ladder architecture (Candidate C) and *against* both the current design (Candidate A) and a single better-chosen-but-still-universal anchor (a simpler version of Candidate B).

## Phase 3 — Candidate selection

- **A (current universal anchor)**: rejected, reproduced failing empirically above.
- **B (single tier-matched anchor)**: insufficient on its own — a single anchor can only serve one tier well; Pokémon far from its magnitude still collapse (this is exactly what happened to Pikachu+Torkoal even at 2 terms).
- **C (anchor ladder, chained pairwise bridge calibration)**: **selected**, per the research spec's own steer and confirmed by evidence, not merely assumed.
- **D (pairwise bridge graph / least-squares)**: not pursued — Phase 7's cost analysis shows the simple chain (Candidate C) adds only ~0.5% request overhead over the current design; the more expensive graph-solving approach is not justified unless a future pass shows the chain is insufficient (e.g., anchor drift between refreshes).

## Phase 5 — Calibration math (implemented in `backend/desirability/trends_anchor_ladder.py`)

```
scale[anchor_0] = 1.0                                  (reference anchor)
scale[anchor_i] = scale[anchor_{i-1}] * (raw_higher / raw_lower)   for each adjacent bridge query
                                                          (calibrate_ladder)

local_relative  = raw_target / raw_local_anchor          (target queried against its assigned rung)
global_relative = local_relative * scale[local_anchor]   (recover_global_relative)
```

Deterministic, monotonic in `raw_target`, no percentile/cohort ranking, no price input (verified by unit test), reproducible from fixed bridge observations only — a stable target's recovered value is provably unaffected by which other targets exist in the same refresh run (`TestCohortIndependence`, verified).

## Phase 6 — Zero classification (implemented, `ZeroClassification` enum)

| Outcome | When |
|---|---|
| `SCORED_ZERO_HIGH_CONFIDENCE` | Zero/near-zero persists after escalation to the most sensitive (lowest) available ladder rung |
| `RESOLUTION_LIMITED_ZERO` | Zero observed against a coarser rung — must retry at a lower rung before being trusted |
| `MISSING_EVIDENCE` | No data returned for the target |
| `FAILED` | Provider call failed/rate-limited |
| `INSUFFICIENT_CALIBRATION` | No ladder rung could be assigned (no tier hint, or ladder not yet calibrated) |

A raw value is never trusted as a genuine zero until it survives a retry at the most sensitive assignable rung — no positive value is fabricated for unresolved cases; they are marked unavailable instead (`classify_zero_outcome` unit-tested for all five outcomes plus precedence rules).

## Phase 7 — Request-volume comparison (arithmetic, no live calls)

| Design | Requests (1,025 Pokémon × 4 timeframes) | Est. runtime (delay only) |
|---|---|---|
| Current (universal anchor) | 1,028 | ~137 min |
| Anchor-ladder (6-rung, one-time bridge calibration) | 1,033 (+0.49%) | ~138 min |
| Anchor-ladder, worst-case (every target needs one escalation retry) | up to +257/timeframe | proportionally longer — expected case is far lower, to be measured empirically |

The ladder calibration itself (5 bridge queries for a 6-anchor chain) is a **one-time, reusable** cost — it does not scale with the Pokémon universe and only needs periodic re-verification (not every refresh). Per-target batching cost is essentially unchanged from the current design.

## Phase 4 — Anchor selection (not finalized)

Per the research spec's explicit instruction ("do not hardcode specific Pokémon until stability/coverage is tested"), this pass designed the calibration *math* and validated it structurally, but did not run the multi-window stability/variance testing needed to lock in a specific 5-6-anchor roster. That is the next concrete step before a real ladder can be calibrated end-to-end (see below).

## What was NOT done in this pass, and why

- **Phase 9 (full 1,025-Pokémon corrected capture)** and **Phase 10 (large-scale anchor-invariance validation)**: not run. At ~137+ minutes of API calls alone (before any rate-limit cooldowns, which the existing code already handles with a 15-minute circuit-breaker cooldown after 3 consecutive 429s), this is a long-running background operation, not something to execute inside a single interactive research/implementation turn — especially given the user's explicit cost-sensitivity instruction. Running it now, unsupervised, risked consuming real Google Trends quota on an unfinished anchor roster (Phase 4 not yet locked).
- **Phase 4 anchor stability testing**: needs its own multi-window live-query pass (repeated measurements of candidate anchors over time) before specific anchors are locked — explicitly instructed not to hardcode without this.
- **Phase 11/12 (composite shadow rebuild, downstream V6 preview)**: gated on Phase 9's full capture; not attempted with placeholder data, to avoid producing numbers that look final but aren't.

## Tests

24 new unit tests in `backend/tests/unit/desirability/test_trends_anchor_ladder.py`, all passing: defect reproduction (live-value fixtures), ladder calibration determinism/error handling, bridge math, batch-choice invariance, zero-retry classification (all 5 outcomes + precedence), cohort independence, no-price-dependency, full-pipeline determinism. Existing `test_google_trends_ingestion.py` (16 tests) still passes unmodified — no regression, no existing code touched. `python -m py_compile` clean, `git diff --check` clean.

## Files produced

- `backend/desirability/trends_anchor_ladder.py` (new, additive-only module)
- `backend/tests/unit/desirability/test_trends_anchor_ladder.py` (new, 24 tests)
- `docs/research/pokemon_trends_anchor_ladder_calibration.md` (this file)

## Commit

`392b7b0a` on `develop`: `feat(desirability): add anchor-ladder calibration for Pokémon Trends`
