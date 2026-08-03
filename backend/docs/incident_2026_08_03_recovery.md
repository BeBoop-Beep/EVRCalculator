# Incident 2026-08-03 — Recovery Runbook

**Status:** prepared, **not executed**. No production state was modified while
preparing this. Every command below must be run deliberately by an operator.

---

## 1. What happened

| Fact | Value |
|------|-------|
| Production market date | 2026-08-03 |
| Expected jobs | 201 |
| Completed | 167 |
| Failed | 34 (all `invalid_set_key_filter`, each attempted 3×) |
| Batch status | `incomplete` — never promoted |
| Last public market date | 2026-08-02 |
| VM commit | `e4ac8208` (`Merge pull request #94`), branch `main`, tree clean |
| VM position | 19 commits behind the newer `main`, fast-forward (no divergence) |

**Root cause: a stale deployed commit.** The VM's checkout predated 37
`otherEra` config files. At `e4ac8208` the `otherEra` registry held 15 keys; on
current `main` it holds 52. All 34 failing canonical keys resolve on `main` and
resolve in **none** of the VM's registry. Branch, working directory, and Python
interpreter were all correct.

Database metadata had been synchronized from a code generation **between** the
VM's commit and current `main`, giving a clean three-way ordering:

```
VM checkout  <  DB metadata  <  current main
   (15 keys)     (201 ready)      (204 old-rule ready / 209 configs)
```

The 3-row gap between the DB's 201 and main's 204 is exactly
`eReaderSampleCards`, `firstPartnerCollection2026`, `me30thCelebration` — the
three newest configs, not yet synced.

**Second, independent defect:** all 37 of those configs are `CATALOG_ONLY`
(promos, trainer kits, product catalogs). They were entering the
publication-critical daily cohort purely because they carried a URL. Under the
corrected cohort rule the daily cohort is exactly **167 sets** — precisely the
167 that succeeded on August 3.

---

## 2. Preconditions

Do not start until **all** of these are true:

- [ ] Code merged to `main`
- [ ] Migration `058_set_lifecycle_flags_and_scrape_runtime_provenance.sql` applied
- [ ] Frontend and backend deployed
- [ ] VM updated to the merged commit (see §13 of `scraper_vm_operations.md`)

---

## 3. Recovery commands

Run on the VM unless stated otherwise.

```bash
cd ~/repos/EVRCalculator
source .venv/bin/activate
```

### Step 1 — Verify the VM now contains the corrected registry

```bash
git rev-parse HEAD                 # must equal the approved merge SHA
git rev-parse --abbrev-ref HEAD    # main
git status --porcelain             # must be empty

# The 34 previously-failing keys must now resolve.
python - <<'PY'
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry
reg = build_valid_set_key_registry()
keys = reg["config_map"]
sample = ["alternateArtPromos", "wotcPromo", "expedition", "battleAcademy",
          "tradingCardGameClassic", "xyTrainerKitSylveonAndNoivern"]
print("total configs:", len(keys))
print("catalog_only :", sum(1 for c in keys.values() if getattr(c, "CATALOG_ONLY", False)))
missing = [k for k in sample if k not in keys]
print("unresolved sample keys:", missing or "none")
PY
```

Expected: `total configs: 209`, `catalog_only: 37`, `unresolved sample keys: none`.

### Step 2 — Metadata sync dry-run

```bash
python backend/scripts/sync_pokemon_eras_and_sets.py
```

Review the report. Confirm in `summary`:

- `total_catalog_only_from_constants: 37`
- `total_scrape_ready_sets_from_constants: 167`
- `catalog_only_marked_ready_count: 0`

### Step 3 — Apply the metadata sync

```bash
python backend/scripts/sync_pokemon_eras_and_sets.py --apply
```

Confirm in `verification`:

- `catalog_only_never_daily_ready: true`
- `catalog_only_marked_ready: []`
- `scrape_ready_count_matches_constants: true`

### Step 4 — Run the runtime preflight; require zero mismatches

```bash
python backend/scripts/audit_pokemon_scrape_runtime.py --json
echo "preflight exit: $?"
```

**Required:** exit `0`, `mismatches.count: 0`, and
`hashes.local_eligible_registry_sha256 == hashes.database_cohort_sha256`.
`counts.database_cohort` should read **167**.

Do not continue on any nonzero exit.

### Step 5 — Re-evaluate the existing 2026-08-03 batch against the corrected cohort

```bash
python backend/scripts/complete_scrape_batch.py --market-date 2026-08-03 --no-repair
```

This is **status only** — it evaluates and does not requeue.

### Step 6 — Confirm the 34 terminal jobs no longer count as missing

The corrected `pokemon_scrape_ready_cohort()` excludes catalog-only sets, so
`pokemon_scrape_missing_sets('2026-08-03')` is computed over the 167 required
sets — all of which already have valid August 3 Near Mint observations.

**Expected:** `missing_set_count: 0`.

The 34 catalog-only jobs remain in the table as terminal `failed` rows with their
real history. Nothing is deleted, and no counter is edited by hand.

> If `missing_set_count` is **not** 0, stop and investigate. Do not force
> completion. The fail-closed gate is working as designed and August 2 stays
> public.

### Step 7 — Complete / promote the existing batch

```bash
python backend/scripts/complete_scrape_batch.py --market-date 2026-08-03
```

`complete_scrape_batch_if_ready` stamps `completed_at` and `promoted_at` **only**
when the cohort is observation-complete.

**Expected:** `status: complete`, `promoted: true`.

### Step 8 — Run coordinated daily publication for 2026-08-03

```bash
python backend/scripts/run_daily_opening_publication.py --market-date 2026-08-03
```

### Step 9 — Run the complete publication audit

```bash
python backend/scripts/audit_pokemon_market_publication.py --market-date 2026-08-03 --json
echo "audit exit: $?"
```

**Required:** exit `0`, `passed: true`, `failed_set_count: 0`.

If any set fails, `failed_by_section` names which of Set Value, Top Chase,
Opening Profit vs Cost, Sealed Market, card prices, or header summary is behind.

---

## 4. Frontend validation

### Step 10 — Phantasmal Flames (the reported set)

1. **Direct Overview URL** — load the set page directly.
2. **Explore → Best Sets to Rip → Phantasmal Flames** — client-side navigation.
3. **Hard refresh** (Ctrl/Cmd-Shift-R) on the Overview URL.
4. **Normal client-side set switch** — navigate to another set and back.

All four must produce the **same** Top Chase state: 10 cards, each with a
rendered trend line. No card may read "Awaiting trend".

### Step 11 — Controls

Repeat the same four checks for **Scarlet & Violet 151** and **Ascended Heroes**.

### Step 12 — Confirm every surface is on the promoted date

For each of the three sets, verify these all show **2026-08-03**:

- [ ] Set Value (history ends on the promoted date; header value matches the final point)
- [ ] Top Chase Cards (trends render; no "Awaiting trend"; no future dates)
- [ ] Opening Profit vs Cost (latest **real** simulation point)
- [ ] Sealed Market (where the set has a mapped sealed product)
- [ ] Card prices / cards snapshot
- [ ] Set-page header summary — must not advertise a date newer than any section

---

## 5. Explicitly forbidden

Do **not** do any of the following. Each of them fabricates freshness or destroys
evidence, and none is required by this recovery:

- ❌ Delete snapshots
- ❌ Truncate history
- ❌ Manually set batch counters
- ❌ Manually set `promoted_at`
- ❌ Copy August 2 observations into August 3
- ❌ Bypass the publication gate

If the pipeline cannot legitimately reach August 3, the correct outcome is that
**August 2 stays public with its truthful as-of date** until the next generation
is produced.
