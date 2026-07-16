# Collector Appeal CA7 — production dry run (Phase 8.1)

**Preview trustworthy: YES** · **Writes performed: 0** · **`--commit` reachable: NO** · Generated 2026-07-16T06:31:19.030607+00:00

> This run reads production and writes nothing. `main()` never passes `commit=True` and exposes no flag that could.

## Identity

- Metric: **`collector_appeal_ca7`** · status **`internal_candidate`** · stored at **`diagnostics_json.collector_appeal_ca7`**
- Formula: **CA7**, λ = **0.5**
- **Old formula fingerprint:** `fbd2ccff9b8286e3dcdaf4e10283647834e3f761daf42341cc1b592d7f382764`
- **New formula fingerprint:** `a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774`
- Normalized payload hash: `298a230164b671fedc793b4433a3818752c1ae8bd77de78d0a55c274562d27de`
- Full source manifest hash: `4c16a4d42efc3346ee9835ffe1e6e553210fbcf6e0d87a45eea4fcfa4047a27a`
  - `component_rows`: `41ac4ff95c88954a42d3b6189179b7b3cf3365f76bcd05de592d017eb9dd6b73`
  - `pull_model`: `fd75a8334f67b4033e4cc2bc9a6176a61d239cd5bcf64cc16b04be6fc19502a1`
  - `card_inputs`: `ebf4722147c9d064756cc51e579e31a4ec096a70b4284bfeff988b2b2dd15ebe`
  - `simulation_cohort`: `821f52842625b241dab19754d2ad820c449f5e244520114c8edb2cfb849612bf`

## Source-version contract

The component table's real unique key is `(set_id, scoring_version, hit_policy_version, composite_scoring_version, fan_popularity_snapshot_id, config_fingerprint)` — **`set_id` is not unique** (511 rows / 171 sets). Rows are selected by EXACT version match, never by recency.

| Expected version | Value |
|---|---|
| scoring_version | `pokemon_set_desirability_components_v2_40_25_20_15` |
| hit_policy_version | `pokemon_card_desirability_hit_policy_v2_coverage_cleanup` |
| composite_scoring_version | `pokemon_desirability_composite_v1` |

### Rows present, by version

| scoring_version | hit_policy_version | composite_scoring_version | rows | sets | selected? |
|---|---|---|---|---|---|
| `pokemon_set_desirability_components_v2_40_25_20_15` | `pokemon_card_desirability_hit_policy_v1` | `pokemon_desirability_composite_v1` | 171 | 171 | no |
| `pokemon_set_desirability_components_v2_40_25_20_15` | `pokemon_card_desirability_hit_policy_v2_coverage_cleanup` | `pokemon_desirability_composite_v1` | 170 | 170 | **YES** |
| `pokemon_set_desirability_components_v2_40_25_20_15` | `pokemon_card_desirability_hit_policy_v2` | `pokemon_desirability_composite_v1` | 170 | 170 | no |

- Exact-version rows found: **170**
- Sets missing an exact-version row: **1**
- Sets with duplicate exact-version rows: **0**

### Sets with no current-version component row

These are **unavailable**, not silently served from an older row.

- **Chaos Rising** (`5bdbfae1-3f2e-44e7-b8c9-1035ad45b896`) — `missing_current_component_source_row` · **RIP-consumed**
  - Available versions:
    - `pokemon_card_desirability_hit_policy_v1` (built 2026-06-16T17:03:14.983277+00:00, id `23ad1e53-11c0-422e-beed-6ef2afcfcf63`)
  - Separate dry-run rebuild command (NOT executed in this task):
    ```bash
    python backend/scripts/build_pokemon_set_desirability_component_scores.py \
      --set-id 5bdbfae1-3f2e-44e7-b8c9-1035ad45b896 \  # Chaos Rising
      --hit-policy-version pokemon_card_desirability_hit_policy_v2_coverage_cleanup \
      --dry-run
    ```

## Counts

| Metric | Value |
|---|---|
| products total | **170** |
| booster supported | **134** |
| unsupported | **36** |
| exact version source rows available | **170** |
| exact version source rows missing | **1** |
| would update | **170** |
| would insert | **0** |
| diagnostics only updates | **170** |
| score changing updates | **0** |
| unchanged | **0** |
| fingerprint current | **0** |
| fingerprint stale | **0** |
| fingerprint missing | **170** |
| collector appeal available | **20** |
| collector appeal unavailable | **150** |
| rip consumed total | **33** |
| rip consumed collector appeal available | **20** |
| rip consumed collector appeal unavailable | **13** |
| rows with warnings | **0** |

## RIP-consumed cohort — CA7 coverage

**20 of 33** RIP-consumed sets can produce a CA7 value. **13** cannot.

> RIP continues to use Universal Desirability v3 at 10%. CA7 is **not** wired into RIP, and no CA7→D fallback is permitted inside one leaderboard: that would rank rows computed from two different constructs against each other.

### RIP-consumed sets WITHOUT CA7

| Set | Reason |
|---|---|
| Astral Radiance | `dual_path_depth_unavailable_no_pull_model` |
| Battle Styles | `dual_path_depth_unavailable_no_pull_model` |
| Brilliant Stars | `dual_path_depth_unavailable_no_pull_model` |
| Chaos Rising | `missing_current_component_source_row` |
| Chilling Reign | `dual_path_depth_unavailable_no_pull_model` |
| Darkness Ablaze | `dual_path_depth_unavailable_no_pull_model` |
| Evolving Skies | `dual_path_depth_unavailable_no_pull_model` |
| Fusion Strike | `dual_path_depth_unavailable_no_pull_model` |
| Lost Origin | `dual_path_depth_unavailable_no_modeled_subject` |
| Rebel Clash | `dual_path_depth_unavailable_no_pull_model` |
| Silver Tempest | `dual_path_depth_unavailable_no_pull_model` |
| Sword & Shield | `dual_path_depth_unavailable_no_pull_model` |
| Vivid Voltage | `dual_path_depth_unavailable_no_pull_model` |

### RIP-consumed sets WITH CA7

| Set | CA7 |
|---|---|
| Ascended Heroes | 0.960942 |
| Black Bolt | 0.851027 |
| Destined Rivals | 0.898659 |
| Journey Together | 0.893347 |
| Mega Evolution | 0.900581 |
| Obsidian Flames | 0.888906 |
| Paldea Evolved | 0.913821 |
| Paldean Fates | 0.957943 |
| Paradox Rift | 0.886375 |
| Perfect Order | 0.847975 |
| Phantasmal Flames | 0.924631 |
| Prismatic Evolutions | 0.946179 |
| Scarlet and Violet 151 | 0.945391 |
| Scarlet and Violet Base Set | 0.796771 |
| Shrouded Fable | 0.567918 |
| Stellar Crown | 0.881232 |
| Surging Sparks | 0.908714 |
| Temporal Forces | 0.88061 |
| Twilight Masquerade | 0.842445 |
| White Flare | 0.881582 |

## Invariants

| # | Invariant | Result |
|---|---|---|
| 1 | every catalogue product is accounted for (planned + unavailable) | ✅ pass |
| 2 | exactly 135 booster-supported across the catalogue | ✅ pass |
| 3 | exactly 36 unsupported non-booster products across the catalogue | ✅ pass |
| 4 | supported and unsupported are disjoint | ✅ pass |
| 5 | the two groups cover every planned row | ✅ pass |
| 6 | no classifier decision depends on the existing score value | ✅ pass |
| 7 | every booster-supported product has a positive existing score | ✅ pass |
| 8 | every unsupported product classified through metadata/evidence | ✅ pass |
| 9 | ranked simulation cohort has full Universal Desirability coverage | ✅ pass |
| 10 | unsupported products have zero overlap with the ranked cohort | ✅ pass |
| 11 | no existing score value changes in the proposed payload | ✅ pass |
| 12 | no score/version/source/simulation/market field changes | ✅ pass |
| 13 | no RIP weight changes | ✅ pass |
| 14 | the payload writes exactly one column and no frontend contract | ✅ pass |
| 15 | CA7 uses lambda = 0.50 everywhere | ✅ pass |
| 16 | every proposed diagnostics payload carries the current fingerprint | ✅ pass |
| 17 | building and normalizing the plan twice yields identical output | ✅ pass |
| 18 | the update plan is exactly the set of missing/stale rows | ✅ pass |
| 19 | no write request was executed | ✅ pass |
| 20 | no migration applied | ✅ pass |
| 21 | every source identity matches its row's ACTUAL versions | ✅ pass |
| 22 | every planned row came from a version-exact source row | ✅ pass |
| 23 | all RIP-consumed rows have Collector Appeal coverage | ⛔ **fail — known rollout blocker** |
| 24 | every update target's primary key exists exactly once in the source state | ✅ pass |
| 25 | CA7 is stored under its own namespaced key, never generic collector_appeal | ✅ pass |
| 26 | the proposed write is a primary-key update, never an upsert | ✅ pass |

### Failed invariants

- **23 — all RIP-consumed rows have Collector Appeal coverage** (known rollout blocker — expected)
  ```json
  {
  "rip_consumed_total": 33,
  "collector_appeal_available": 20,
  "collector_appeal_unavailable": 13,
  "unavailable_sets": [
    {
      "set_id": "0d90b4ed-16a1-456c-81c6-83d2869d3846",
      "set_name": "Astral Radiance",
      "set_canonical_key": "astralRadiance",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "46ab39a7-dd96-4a2d-af0f-44b868918114",
      "set_name": "Battle Styles",
      "set_canonical_key": "battleStyles",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "a72c75bd-0d61-4643-b603-fef78425dcfa",
      "set_name": "Brilliant Stars",
      "set_canonical_key": "brilliantStars",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "5bdbfae1-3f2e-44e7-b8c9-1035ad45b896",
      "set_name": "Chaos Rising",
      "set_canonical_key": "chaosRising",
      "collector_appeal_ca7": null,
      "reason": "missing_current_component_source_row"
    },
    {
      "set_id": "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890",
      "set_name": "Chilling Reign",
      "set_canonical_key": "chillingReign",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "3836457c-77dc-44b0-a72f-779b6dd78884",
      "set_name": "Darkness Ablaze",
      "set_canonical_key": "darknessAblaze",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "93212749-ce0e-498e-975e-7d947a3448ce",
      "set_name": "Evolving Skies",
      "set_canonical_key": "evolvingSkies",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "8cd0a0f0-d17c-4a5c-bc52-47e1723e0699",
      "set_name": "Fusion Strike",
      "set_canonical_key": "fusionStrike",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "5109f22e-0799-46b5-a4ad-8861d1cfefee",
      "set_name": "Lost Origin",
      "set_canonical_key": "lostOrigin",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_modeled_subject"
    },
    {
      "set_id": "759c09f8-8a1b-4212-be89-66088afa6893",
      "set_name": "Rebel Clash",
      "set_canonical_key": "rebelClash",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "2d6ec108-70b2-4698-a21a-1af39828004f",
      "set_name": "Silver Tempest",
      "set_canonical_key": "silverTempest",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "cbc11b3c-0244-4fca-880f-68ebdd599894",
      "set_name": "Sword & Shield",
      "set_canonical_key": "swordAndShield",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    },
    {
      "set_id": "26fedb88-87d7-487a-9f01-528d603c682e",
      "set_name": "Vivid Voltage",
      "set_canonical_key": "vividVoltage",
      "collector_appeal_ca7": null,
      "reason": "dual_path_depth_unavailable_no_pull_model"
    }
  ],
  "blocker_note": "Expected to fail while only part of the ranked cohort is pull-modeled. This blocks wiring CA7 into RIP; it does not invalidate CA7 on the sets it covers. No CA7 -> D fallback is permitted inside one leaderboard."
}
  ```

## Future write strategy — NOT EXECUTED

- Method: **update** by primary key, **1 row per statement**
- Predicate: `id = <source_row_id> AND updated_at = <expected_updated_at>`
- Writable columns: `['diagnostics_json']`
- Upsert: FORBIDDEN. set_id is not unique in this table (511 rows / 171 sets), so on_conflict="set_id" names no constraint and cannot identify a row.
- Concurrency: optimistic: updated_at is pinned in the predicate, so a row that moved since the preview matches zero rows and fails instead of overwriting.
- Zero rows returned → fails - the target vanished or moved
- More than one row returned → fails - the predicate was not unique
- Idempotent: yes - a second run re-reads state, finds the fingerprint current, and plans zero updates

```python
client.table("pokemon_set_desirability_component_scores").update({"diagnostics_json": proposed_diagnostics}).eq("id", source_row_id).eq("updated_at", expected_updated_at).execute()
```

A future commit command would require ALL THREE approval tokens to match a rebuilt plan:

```bash
  --expected-fingerprint a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774
  --expected-manifest 4c16a4d42efc3346ee9835ffe1e6e553210fbcf6e0d87a45eea4fcfa4047a27a
  --expected-payload-hash 298a230164b671fedc793b4433a3818752c1ae8bd77de78d0a55c274562d27de
```

**No such command exists yet.** `--commit` is not implemented in this script.

## Pagination

- Pages read: 1 · total rows 511
- Final page partial (proves no truncation): **True**
- Truncation possible: **False**

## Read-only evidence

- Mutating client methods attempted: **0** 
- Writes performed: **0**
- Tables read: explore_rip_statistics_latest, pokemon_canonical_cards, pokemon_card_desirability_links, pokemon_desirability_composite_scores, pokemon_set_desirability_component_scores, pokemon_set_page_snapshot_latest

## Anomalies

None.
