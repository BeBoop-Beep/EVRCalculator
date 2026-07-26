# Desirability Refresh + Collector Appeal Rollout

**Status: pipeline repaired and unified. No migration applied. No scheduled task
created. No RIP weight changed. No production write performed by this work.**

- Date: 2026-07-15. Branch: `research/desirability-card-study`.
- Orchestrator: `backend/scripts/run_desirability_refresh.py`.
- Anchor repair: `backend/desirability/trend_anchor_tiers.py`.
- Tests: `backend/tests/unit/desirability/test_desirability_refresh.py` (36).
- Prior phases: `factorized-opening-appeal-results.md`,
  `collector_appeal_market_prediction_results.md`.

---

# EXECUTIVE SUMMARY

## The pipeline was not conceptually broken. It had an uninstalled dependency and a badly chosen anchor term.

Both root causes are now identified with direct measurement, and one of them
also explains the desirability compression the previous phase flagged.

**1. `pytrends` was declared in `requirements.txt` but not installed in
`backend/.venv`.** Every Trends run exited `provider_unavailable`. Installing it
(nothing else) produced a clean capture: **60/60 subjects, 0 rate-limited
batches, 0 failed batches**.

**2. The `Pikachu` anchor destroys the signal for most of the roster.** This is
the finding that matters. Measured live, same three subjects, `today 1-m`, geo
US, only the anchor changed:

| Anchor | Brambleghast | Varoom | Rabsca |
|---|---|---|---|
| **Pikachu** | **0.00** | **0.03** | **0.06** |
| **Bisharp** | **3.29** | **10.90** | **10.74** |

Google Trends returns a *relative* index: the top term in a request becomes 100
and everything else is scaled against it. Pikachu is roughly 70× Bisharp, so
every less-popular subject rounds into the bottom bin.

**The "49.7% of subjects have trend score 0" finding was never real.** The
composite builder reports `trend_scores_found: 1025`, `missing_trend_count: 0` —
all 1,025 subjects *were* captured. Those zeros are a **measurement artifact of
anchor dominance**, not an absence of collector interest.

**This single cause explains the desirability compression too.** With trend
zeroed for half the roster, `D = 0.75·fan_popularity + 0.25·trend` collapses onto
its static component — which is exactly the `corr(D, fan_popularity) = 0.9887`
and the 16-of-21-sets-in-a-0.15-band clustering the previous phase measured. §10
and §4 are the same bug.

## What is ready, and what is not

- **Ready:** one command runs the whole refresh, dry by default, with locking,
  quality gates, checkpoints, structured exit codes and a JSON manifest.
- **Ready:** the Task Scheduler command (below). **The task is not created** —
  you configure it after review.
- **Not done in this phase, and I want to be direct about it:** Sections 6–12
  (productionizing the appeal metrics into canonical RIP, the June 11 forward
  pilot, the recovery pilot, effective-influence analysis, and the preference-
  study design) are **not implemented**. The diagnosis and repair consumed the
  phase. Those sections are unstarted, not silently partial — see
  *§Deferred work* for exactly where they stand.

---

# SECTION 2 — ROOT-CAUSE TABLE

Every row was reproduced by running the real scripts in `backend/.venv`.

| # | Symptom | Exact failing command | Root cause | Category | Fix | Status |
|---|---|---|---|---|---|---|
| 1 | Trends returns nothing; `status: provider_unavailable` | `ingest_pokemon_trends.py --dry-run --provider pytrends --limit 4` | `pytrends==4.9.2` declared in `requirements.txt` but **absent from `backend/.venv`** | **Undeclared/uninstalled dependency** | `pip install pytrends==4.9.2` (venv now matches the existing pin) | **Fixed & verified** |
| 2 | ~half the roster scores trend = 0 | n/a — silent, not an error | **`Pikachu` anchor dominance.** Trends' 0–100 index is relative; Pikachu ≈ 70× a mid-tier subject, so the rest round to 0 | **Anchor failure (measurement artifact)** | Tiered anchors + bridge rescaling (`trend_anchor_tiers.py`) | **Diagnosed, module built, not yet wired into ingest** |
| 3 | `D` ≈ static fan popularity (ρ 0.9887); sets compressed into a 0.15 band | n/a | **Downstream of #2.** A zeroed trend component cannot differentiate anything | **Consequence of #2** | Fix #2 first, then re-measure | **Explained; awaits #2 wiring** |
| 4 | June 11 snapshot had `rate_limited_gracefully` on `today 12-m` | n/a (historical) | Genuine 429 on the 12-month window during that run | **Rate limiting** | Bounded retry + cooldown already existed; orchestrator now **gates** on it instead of promoting a partial capture | **Gated** |
| 5 | Environment not reproducible | `pip install -r backend/requirements.txt` | **`requirements.txt` pins `pandas==2.2.3`; venv has `pandas 3.0.1`** | **Dependency drift** | Reconcile deliberately — see the warning below | **Reported, NOT changed** |
| 6 | Several scripts must be run in the right order by hand | — | No orchestrator existed | **Operational** | `run_desirability_refresh.py` | **Fixed** |

### Things that were NOT the cause (checked and cleared)

- **Working-directory assumptions** — every script already resolves
  `REPO_ROOT = Path(__file__).resolve().parents[2]` and injects it on `sys.path`.
- **Missing environment values** — `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_ANON_KEY`, `JWT_SECRET` all present and loading from `backend/.env`.
- **Database connectivity / missing tables** — preflight verifies all 8 required
  tables; all returned OK.
- **Batch size / retry logic** — already implemented (`--batch-size`,
  `--max-retries`, `--retry-backoff-seconds`, `--stop-after-consecutive-429s`,
  `--cooldown-after-429-seconds`).
- **Missing data treated as zero** — the *ingest* layer was clean here. The
  zeros came from a healthy request against a bad anchor, which is a subtler and
  more dangerous failure: the data looked valid.

### ⚠️ Dependency drift — needs your decision, not my guess

`requirements.txt` pins **`pandas==2.2.3`**. The venv actually runs **`pandas
3.0.1`**. `pandas` is imported throughout the EVR calculation code
(`evrCalculator.py`, `rarity_classification.py`, `hit_value_metrics.py`, and
more). So:

> Rebuilding the venv from `requirements.txt` today would **downgrade pandas to
> 2.2.3 and produce a different environment from the one your production
> calculations currently run under.** pandas 3.0 changed copy-on-write defaults.

I did **not** change the pin. Verifying which version the EVR calcs are correct
under is its own task, and silently editing the pin would make the discrepancy
harder to find, not easier. `pytrends 4.9.2` was verified working against pandas
3.0.1 (live requests succeeded), so this does not block the refresh.

---

# SECTION 3 — THE UNIFIED ORCHESTRATOR

`backend/scripts/run_desirability_refresh.py` is the only script the scheduled
task calls. It resolves the repo root itself and runs every child stage with
`sys.executable`, so **no venv activation is needed**.

**Stage order** (asserted by test):

```
preflight -> trends -> static -> composite -> links -> sets -> snapshot -> report
```

| Stage | Does | Gate |
|---|---|---|
| `preflight` | env, dependency versions, DB connectivity, all 8 tables, advisory lock | fails fast, exit 2 |
| `trends` | Google Trends via pytrends | **rate-limited ⇒ refuse to promote**; failure ratio ≤ 10% |
| `static` | fan popularity — **only when > 30 days old** or `--force-static` | skipped when fresh |
| `composite` | rebuild `D` from valid observations only | fan coverage ≥ 95% |
| `links` | card→subject links | — |
| `sets` | set-level component scores | — |
| `snapshot` | append-only history | **`blocked` (not failed) when migration 046 is absent** |

**Verified behaviours:**

```
$ run_desirability_refresh.py --stage snapshot
[preflight] ok in 2.3s          <- all 8 tables verified
[snapshot] skipped in 0.5s      <- correctly reports 'blocked', migration absent
exit=0                          <- DRY RUN, nothing written

$ (with a concurrent lock planted)
Run aborted: Another run holds the lock (run_id=FAKE-CONCURRENT, pid=999999). Refusing to start.
exit=3
```

**Exit codes** (so Task Scheduler's "Last Run Result" is meaningful):

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | preflight failed (deps/env/DB/tables) |
| 3 | another run holds the lock |
| 4 | source quality gate failed (e.g. rate-limited) |
| 5 | a stage failed |
| 6 | validation gate failed |
| 130 | interrupted |

Also implemented: bounded retries with exponential backoff **and jitter**;
per-stage timeouts; checkpointing with `--resume <run_id>`; log retention capped
at 60 runs; unique run IDs; no silent exception swallowing (every failure carries
its traceback into the manifest).

**Dry run is the default.** `--commit` is required to write.

---

# SECTION 4 — TRENDS: CADENCE, MEASURED

Measured throughput: **60 subjects, 1 timeframe, 3m12s** ⇒ 15 batches ⇒
**~12.8 s/batch** (8 s delay + ~4.8 s request), **0 rate-limited**.

Extrapolated to the full roster (1,025 subjects, batch size 5 = 4 subjects +
anchor ⇒ **257 batches per timeframe**):

| Scope | Batches | Estimated wall time |
|---|---|---|
| 1 timeframe | 257 | **~55 min** |
| 3 timeframes (what the composite requires: 1-m, 12-m, 5-y) | 771 | **~2.7 h** |
| All 4 configured timeframes | 1,028 | **~3.7 h** |

**Can it support 1,025 subjects on a Mon/Wed/Fri cadence? Probably — but this is
an extrapolation from 15 clean batches, not a measured full run.** Google's
limits are time-windowed; 257 consecutive batches is a materially different
proposition from 15. The orchestrator therefore **gates rather than gambles**: a
rate-limited capture fails with exit 4 and leaves existing good data in place.

**Recommended cadence, given the measurement:**

- `today 1-m` + `today 12-m` (the two the composite actually consumes) on
  **Mon/Wed/Fri** ⇒ ~1.8 h/run.
- `today 5-y` **monthly** — a 5-year baseline cannot move meaningfully in 48 h.
- Fan popularity **monthly** (`STATIC_MAX_AGE_DAYS = 30`), already enforced.

**What should NOT be refreshed three times a week:** the favoritepokemon
fan-popularity poll. It moves on a scale of months and re-scraping it adds a
browser-automation failure surface to every run for no new information. The
orchestrator skips it unless it is >30 days old or `--force-static` is passed.

## The anchor repair (`trend_anchor_tiers.py`)

Tiers, anchors and bridges — fixed constants, chosen from *static fan-popularity
rank only* (never from the trend being measured, which would be circular; a test
asserts this):

```
tier 0 mega   rank    1-25    anchor Pikachu    bridge Charizard
tier 1 high   rank   26-100   anchor Charizard  bridge Lucario
tier 2 mid    rank  101-300   anchor Lucario    bridge Bisharp
tier 3 low    rank  301-650   anchor Bisharp    bridge Klefki
tier 4 niche  rank  651+      anchor Klefki     bridge —
```

Each tier is chained onto the one above via a bridge term measured in both. When
a bridge reads below the resolution floor the tier is marked **`unscaled_tier`**
rather than assigned an invented factor.

**Explicit statuses**, so a failure can never again masquerade as a zero:
`valid`, `genuine_zero`, `missing`, `rate_limited`, `incomplete`,
`anchor_failure`, `stale_fallback`, `unscaled_tier`. Coverage reporting counts
`genuine_zero` as *usable* and every failure status as *not usable* — they are
different facts and are never pooled.

**Honest status: the module is built and unit-tested but is NOT yet wired into
`ingest_pokemon_trends.py`.** Wiring it changes what `D` means, so it needs the
side-by-side comparison in §6 that this phase did not reach. Until then the
shipped single-anchor behaviour is unchanged and the zeros persist.

---

# SECTION 5 — WINDOWS TASK SCHEDULER

**Do not create the task from this document blindly — review it first. Nothing
has been scheduled.**

| Field | Value |
|---|---|
| **Program/script** | `D:\EVRCalculator\backend\.venv\Scripts\python.exe` |
| **Add arguments** | `D:\EVRCalculator\backend\scripts\run_desirability_refresh.py --commit` |
| **Start in** | `D:\EVRCalculator` |

`Start in` is belt-and-braces only — the script resolves its own repo root, so it
works even when Task Scheduler launches with `C:\Windows\System32` as the working
directory.

### schtasks.exe template

Replace `HH:MM` with your chosen time. A window after **02:00** is sensible: the
run takes ~2 h and Trends throttles less overnight.

```bat
schtasks /Create ^
  /TN "inDex\DesirabilityRefresh" ^
  /TR "\"D:\EVRCalculator\backend\.venv\Scripts\python.exe\" \"D:\EVRCalculator\backend\scripts\run_desirability_refresh.py\" --commit" ^
  /SC WEEKLY /D MON,WED,FRI /ST HH:MM ^
  /RL HIGHEST /F
```

### PowerShell equivalent (exposes the settings schtasks cannot set)

```powershell
$Action = New-ScheduledTaskAction `
  -Execute 'D:\EVRCalculator\backend\.venv\Scripts\python.exe' `
  -Argument 'D:\EVRCalculator\backend\scripts\run_desirability_refresh.py --commit' `
  -WorkingDirectory 'D:\EVRCalculator'

$Trigger = New-ScheduledTaskTrigger -Weekly `
  -DaysOfWeek Monday,Wednesday,Friday -At 'HH:MM'   # <-- choose the time

$Settings = New-ScheduledTaskSettingsSet `
  -MultipleInstances IgnoreNew `        # never start a second instance
  -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 30) `
  -StartWhenAvailable `                 # catch up if the machine was off
  -WakeToRun `
  -DontStopOnIdleEnd

Register-ScheduledTask -TaskName 'inDex\DesirabilityRefresh' `
  -Action $Action -Trigger $Trigger -Settings $Settings `
  -RunLevel Highest -Description 'inDex desirability refresh (Mon/Wed/Fri)'
```

To run whether or not you are logged on, add `-User`/`-Password`, or set it in
the GUI under *Security options → Run whether user is logged on or not*.

Settings map to your requirements: **IgnoreNew** = do not start a second
instance (the script also holds its own lock as defence in depth);
**ExecutionTimeLimit 6 h** > the ~2 h expected run; **RestartCount 2** = retry
after failure; **WakeToRun**; history is enabled via
`wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true`.

### Manual smoke test (run this first, it writes nothing)

```bat
"D:\EVRCalculator\backend\.venv\Scripts\python.exe" ^
  "D:\EVRCalculator\backend\scripts\run_desirability_refresh.py" --stage snapshot
```

Then a real dry run of the whole pipeline:

```bat
"D:\EVRCalculator\backend\.venv\Scripts\python.exe" ^
  "D:\EVRCalculator\backend\scripts\run_desirability_refresh.py" --dry-run --trend-limit 20
```

### Verifying the last run

```powershell
# Exit code Task Scheduler saw
(Get-ScheduledTaskInfo -TaskName 'inDex\DesirabilityRefresh').LastTaskResult

# Newest manifest: stages, gates, row counts, whether writes occurred
Get-ChildItem 'D:\EVRCalculator\logs\desirability-refresh\*.json' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
  Get-Content -Raw | ConvertFrom-Json |
  Select-Object run_id, exit_code, requested_mode, writes_occurred,
                successful_stages, failed_stages, duration_seconds
```

`exit_code` 0 = success; **4 = Trends was rate-limited and the run correctly
refused to overwrite good data** (re-run later, this is not corruption);
3 = an overlapping run.

---

# SECTION 14 — TESTS RUN

| Suite | Result |
|---|---|
| `test_desirability_refresh.py` (**new**, 36) | **35 passed, 1 skipped** → **36 passed** once this doc existed |
| `backend/tests/unit/desirability` (full) | **241 passed, 1 skipped** |
| Frontend contract tests | **NOT RUN — no frontend or payload code was touched** |

New coverage: stage ordering; repo-root discovery; dry-run default; commit/dry-run
mutual exclusion; lock acquisition, release, stale-lock breaking, corrupt-lock
recovery; bounded retries; `KeyboardInterrupt` never retried; rate-limit gating;
static-source cadence and `--force-static`; checkpoint round-trip; resume of an
unknown run failing loudly; snapshot `blocked` guard; bounded log retention;
**failed retrieval never becoming a genuine zero**; failures never pooled with
genuine zeros; stale-fallback marking; resolution-floor confidence; tier
contiguity; anchor never duplicated in a payload; bridge ratio refusing to invent
a factor; tier assignment never touching price or the trend it measures; and
scheduler-doc/CLI consistency.

---

# DEFERRED WORK — stated plainly

These brief sections are **not started**. I am not going to present a diagnosis
phase as if it covered them.

| Section | Status | Why | What it needs |
|---|---|---|---|
| 6 — productionize appeal metrics into canonical RIP at 10% | **Not started** | Wiring `collector_appeal` into RIP requires the side-by-side old/new comparison for all 21 sets first, and that comparison is only meaningful *after* the anchor fix lands (§4), because the fix changes `D` | Wire anchors → re-measure `D` → side-by-side → then integrate |
| 7 — product representation | **Not started** | Frontend/payload work; none touched | Depends on §6 |
| 8A — June 11 forward pilot | **Not started** | The highest-value analysis still open. Data exists: snapshot `observed_on` 2026-06-11, prices through 2026-07-15 = **34 days** ⇒ 7/14/30-day horizons are all reachable | Grouped-by-set/subject clustering; strictly post-06-11 prices |
| 8B — retrospective association | **Not started** | — | Must be labelled descriptive, never predictive |
| 8C — recovery pilot | **Not started** | 34 days post-snapshot supports 7/14/30-day recovery windows only | Report exact event counts; stop if underpowered |
| 9 — immutable prospective baseline | **Partially specified** | Migration 046 defines the tables; cohort-immutability rules are not implemented | Apply 046, then implement cohort freeze |
| 10 — compression investigation | **Root cause found, decomposition not run** | The cause is the anchor (§4). The formal decomposition into Chase Subject Strength/Depth/Coverage was not run | Re-measure after the anchor fix — decomposing today would just re-measure the artifact |
| 11 — effective RIP influence | **Not started** | — | Needs §6 |
| 12 — preference study design | **Not started** | — | Still the decisive missing evidence |

**§10 deserves emphasis:** decomposing `D`'s compression *before* fixing the
anchor would measure the bug, not the construct. The compression is not
(primarily) a formula defect — it is 512 subjects whose trend component was
rounded to zero. Fix the measurement, then decide whether the formula still
needs bands, tiers, or tied ranks.

---

# ANSWERS TO THE FINAL QUESTIONS

1. **Why were the scripts failing?** `pytrends` was declared in
   `requirements.txt` but not installed, so every Trends run exited
   `provider_unavailable`. Separately (and worse, because it was silent), the
   `Pikachu` anchor rounds most of the roster to 0.
2. **Can the whole refresh run through one command?** Yes —
   `run_desirability_refresh.py`. Verified for preflight/snapshot/lock paths.
3. **Is it safe to run Mon/Wed/Fri?** Yes. Dry by default, locks against
   overlap, gates on source quality, and refuses to promote a partial capture.
   The full-roster runtime (~2 h) is an extrapolation from 15 clean batches, so
   watch the first live run.
4. **What should happen when Trends is rate-limited?** Exit **4**, write
   nothing, leave the previous good data in place. Never record the gap as zero.
5. **What percentage of subjects received valid trend data?** **100%
   (1,025/1,025)** were *captured* — `missing_trend_count: 0`. But ~**49.7%**
   were rounded to 0 by anchor dominance, so they are captured-but-uninformative.
   That is an artifact, not "no interest".
6. **What should not be refreshed 3×/week?** The favoritepokemon fan-popularity
   poll. Now gated to a 30-day cadence.
7. **Is Collector Appeal safely integrated at 10%?** **No — not integrated.**
   Not started (§6). The weight remains 10% Universal Roster Appeal, unchanged.
8. **How much does replacing Roster Desirability with Collector Appeal change
   RIP?** Not measured this phase. Prior research: `CA6 @ 10%` moved max 3 ranks,
   mean 0.38.
9. **Does Collector Appeal have meaningful influence at 10%?** Not measured this
   phase. Prior evidence suggests **barely** — which is the open question §11
   exists to settle.
10. **Is Chase Appeal available separately?** Not yet productionized; it exists
    as a validated research construct.
11. **Are Dual-Path examples correct for Ascended Heroes?** Not verified —
    `dual_path_depth` is implemented and unit-tested on synthetic archetypes, but
    the Ascended Heroes Dragonite/Gengar case was not checked against real data.
12. **Does the June 11 snapshot associate with 7/14/30-day movement?** **Not
    tested.** 34 days of post-snapshot prices exist, so it is answerable — it is
    the top deferred item.
13. **Does any result survive rarity/price/set controls?** Not tested this phase.
14. **Is there enough post-snapshot history for recovery?** 34 days ⇒ 7/14/30-day
    windows only. 90/180-day remain impossible.
15. **What is descriptive rather than predictive?** Anything using the 415-day
    top-chase panel (membership selected by price rank) and any backcast of
    current desirability onto earlier prices.
16. **What should begin snapshotting immediately?** Nothing yet — **fix the
    anchor first**. Snapshotting today's anchor-crushed `D` would archive the
    artifact. Fix (§4 wiring) → verify → apply 046 → then capture.
17. **What blocks validated prediction?** Appeal history (1 observation), 98 days
    of price history, and no volume/liquidity/population/reprint data anywhere.
18. **Exact Task Scheduler command?** See §5. Program
    `D:\EVRCalculator\backend\.venv\Scripts\python.exe`, arguments
    `D:\EVRCalculator\backend\scripts\run_desirability_refresh.py --commit`,
    start in `D:\EVRCalculator`.
19. **What manual action remains?** (a) Decide the pandas pin discrepancy;
    (b) run the smoke test; (c) create the scheduled task and pick a time;
    (d) decide whether to wire the tiered anchors before the first committed run.
20. **Highest-value next step?** **Wire the tiered anchors into
    `ingest_pokemon_trends.py` and re-measure `D`.** It is the gate on everything
    else: it fixes the zeros, very likely fixes the compression, and makes the §6
    RIP comparison meaningful. The June 11 forward pilot is the best *analysis*
    available right now and needs no new data.

---

# FILES CHANGED

| File | Status | Purpose |
|---|---|---|
| `backend/scripts/run_desirability_refresh.py` | **added** | The unified orchestrator |
| `backend/desirability/trend_anchor_tiers.py` | **added** | Tiered anchors, bridge rescaling, explicit statuses |
| `backend/tests/unit/desirability/test_desirability_refresh.py` | **added** | 36 tests |
| `docs/research/desirability_refresh_collector_appeal_rollout.md` | **added** | This document |
| `backend/.venv` | **modified** | `pytrends==4.9.2` installed (brings the venv into line with the existing pin) |

Not changed: `requirements.txt` (the pandas pin discrepancy is reported, not
silently edited); RIP weights; any production module, payload or frontend file;
any database object. Migration 046 remains **unapplied**. No scheduled task was
created.
