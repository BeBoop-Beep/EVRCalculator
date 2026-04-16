# Monte Carlo Simulation V2 Implementation Note

## Architecture
- Added a new state-first simulation engine in backend/simulations/monteCarloSimV2.py.
- Normal packs are modeled as named pack states with explicit slot outcomes (rare, reverse_1, reverse_2).
- Phase 3 extracted pack-state model selection into orchestration helpers under backend/simulations/utils/packStateModels/.
- The simulator no longer owns Scarlet & Violet model building logic.
- God packs and demi-god packs are separate entry paths and bypass normal-state logic.
- run_simulation_v2() uses a single simulation loop so values, counters, and summary metrics come from the same pack set.
- Added optional debug export in run_simulation_v2(export_debug_df=True) for per-pack state analytics.

## Resolution Order
- Pack-state model resolution is now centralized in resolve_pack_state_model(config).
- Resolution precedence:
  1. config.get_pack_state_model() when present and non-empty
  2. config.PACK_STATE_MODEL when present and non-empty
  3. dynamic era builder via normalized config.ERA name
  4. build_base_pack_state_model fallback only when ERA is blank or unspecified

## Namespace-Constrained Lookup
- Era builder resolution is intentionally constrained to the dedicated eraPackStateBuilders namespace.
- The orchestrator does not scan arbitrary modules, recurse the package tree, or reflect across the codebase.
- This keeps lookup deterministic, auditable, and stable for future era onboarding.
- Unsupported named eras now fail loudly with a clear error instead of silently receiving a generic fallback model.

## Builder Naming Convention
- Era builders follow: build_<normalized_era_key>_pack_state_model
- Example: build_scarlet_and_violet_pack_state_model
- New era support requires adding a matching builder function in eraPackStateBuilders.py imports/namespace; orchestrator dispatch remains unchanged.
- Whole-codebase reflection was rejected to avoid hidden magic and accidental builder collisions.

---

## Phase 4 Corrective Refactor: Derived State Probabilities

### Why manual state probabilities were removed

The original Phase 4 implementation introduced `SV_DEFAULT_STATE_PROBABILITIES` and
corresponding set-level probability tables in each `get_*_pack_state_overrides()` function.
These were scaffolding values — manually entered guesses with no researched source.
Every set probability must be either:

1. **Derived** from the set config's own researched slot probability tables, or
2. **Explicitly sourced** from a published pull-rate reference (linked in config comments), or
3. **Empirically estimated** from observed data, clearly labeled as such.

The scaffolding tables satisfied none of these conditions and have been removed.

### Set config as source of truth

Each set config already contains the researched inputs:
- `RARE_SLOT_PROBABILITY` — per-rarity probability for the rare slot
- `REVERSE_SLOT_PROBABILITIES` — per-rarity probability for slot_1 (reverse_1) and slot_2 (reverse_2)

These tables are the single source of truth for probability inputs. They are not
duplicated into the era builder or override layer.

### How state probabilities are now derived

A new utility, `derivePackStateProbabilities.py`, implements the derivation algorithm:

**Step 1 – Enumerate all raw slot combinations:**
For every triple `(rare_rarity, r1_rarity, r2_rarity)` from the cross-product of the
three slot probability tables.

**Step 2 – Multiply within a combination (AND rule):**
```
p_combination = p(rare_rarity) × p(r1_rarity) × p(r2_rarity)
```

**Step 3 – Coerce to a legal outcome:**
Apply the same constraint rules used by the live simulation engine (Rules 1–5
from monteCarloSimV2._coerce_slot_outcomes):
- Rule 1: exclusive hit anywhere → singleton pack (keep only the exclusive)
- Rule 2: IR + exclusive cannot coexist
- Rule 3: at most max_exclusive_hits exclusives
- Rule 4: at most max_major_hits (primary + exclusive) major hits
- Rule 5: at most max_non_regular_hits total non-regular hits

**Step 4 – Name the coerced triple:**
Reverse-lookup into the structural state_outcomes registry (registered state names → slot shapes).
If the coerced triple does not match any registry entry, it is auto-named from
its rarity slugs (e.g., `double_rare_illustration_rare`).

**Step 5 – Add across combinations that collapse to the same state (OR rule):**
```
p[state] += p_combination
```
Multiple raw combinations can coerce to the same named state. For example,
`(double_rare, reg, SIR)` and `(ultra_rare, reg, SIR)` both satisfy Rule 1
(exclusive in slot_2) and collapse to `sir_only = (rare, reg, SIR)`. Their
raw probabilities are summed. This means:
```
P(sir_only) = P(SIR in slot_2) × 1 × 1 = P(SIR in slot_2)
```
regardless of what else appears in the rare or reverse_1 slots.

The final `p[state]` map sums to exactly 1.0 within float precision because every
raw combination contributes to exactly one coerced state.

### Era-level slot defaults

When a set config does not yet define `RARE_SLOT_PROBABILITY` or
`REVERSE_SLOT_PROBABILITIES` (e.g. Ascended Heroes, Mega Evolution, which have
empty PULL_RATE_MAPPING at time of writing), the builder falls back to
`SV_ERA_DEFAULT_RARE_SLOT_PROBABILITY` and `SV_ERA_DEFAULT_REVERSE_SLOT_PROBABILITIES`.

These era defaults are sourced from the Scarlet & Violet Base Set (sv1) which has
published pull-rate research. They are not invented constants.

For sets currently using era defaults, states like `mega_hyper_only` or
`reverse_1_ultra_plus_rare` (which require mega hyper rare in slot_1) will have
probability zero and be pruned from the model. This is correct: it avoids
inventing a probability. Once real slot data is published and added to the config,
the derivation produces the correct probability automatically.

### Override responsibility

Set overrides (`get_*_pack_state_overrides()`) now contain only structural information:

- **New state outcome shapes**: registers a canonical name for a slot combination
  that emerges from the set's slot probabilities but is not in the era default registry.
  Example: `pattern_plus_double_rare` for PRE tells the derivation to name the
  `(double rare, poke ball pattern, regular reverse)` combination that arises
  from PRE's slot_1 data.
- **Constraint additions**: extends `exclusive_hits`, `bonus_hits`, etc.
- **Slot placement changes**: adds state shapes for reverse_1-hosted rarities
  (Ascended Heroes / Mega Evolution) or rare-slot specialties (Black Bolt / White Flare).

Overrides do NOT provide `state_probabilities`. Any `state_probabilities` key in
an override dict is silently discarded by the builder — derivation always takes precedence.

### Mega Hyper Rare handling

`mega hyper rare` is handled through the normal exclusive-hit pipeline without
special-case engine branches:

1. The set override adds `mega hyper rare` to the `exclusive_hits` constraint.
2. The derivation's coercion (Rule 1) treats it identically to `hyper rare` or
   `special illustration rare` — it forces a singleton exclusive pack.
3. The state `mega_hyper_only` is registered in the override's `state_outcomes`
   with reverse_1 (since AH/ME places it there) so the reverse lookup names it correctly.

No parallel engine logic was added. The rarity name change from `hyper rare` to
`mega hyper rare` is handled entirely through the constraint category and state registry.

### Validation

After derivation, `validate_pack_state_model` enforces:
- state probabilities sum to 1.0 (±1e-8)
- every probability-bearing state has complete slot outcomes
- every state_outcome has a corresponding probability (states with zero derived
  probability are pruned before the model is returned)
- derived states respect all constraint rules (exclusive singleton, IR incompatibility, max-hit limits)
- all slot rarities reference cards available in the hit pool

### Key files changed

| File | Change |
|---|---|
| `simulations/utils/packStateModels/derivePackStateProbabilities.py` | NEW — derivation utility |
| `simulations/utils/packStateModels/scarletAndVioletPackStateModel.py` | Removed `SV_DEFAULT_STATE_PROBABILITIES`; builder now derives |
| `simulations/utils/packStateModels/scarletAndVioletSetOverrides.py` | Removed all `state_probabilities` from override functions |
| `tests/unit/simulations/test_pack_state_model_overrides.py` | New requirement-driven tests; old placeholder-based tests replaced |

## Phase 4 Cleanup Pass

### Duplicate slot-outcome aliases are now forbidden

State naming is driven by the normalized slot-outcome triple:

```
(rare, reverse_1, reverse_2)
```

Silent alias collisions (two different state names mapped to the same tuple) are
no longer allowed. They previously depended on dictionary overwrite/insertion
order and could silently re-route probabilities to the wrong state name.

Validation now raises a clear error when duplicates are detected, including:
- the conflicting state names
- the exact normalized tuple that collided

Duplicate-shape validation is applied at:
- Scarlet & Violet era default registry construction
- post-override registry merge
- final derived state registry
- resolved model validation in the simulation path

### ERA ownership layering

ERA ownership is defined at the **era base config** layer, not duplicated on every
set config in that era.

- Shared root base config (`backend/constants/tcg/pokemon/sharedBaseConfig.py`) is era-neutral with `ERA = ""`
- Scarlet & Violet era base config owns: `ERA = "Scarlet and Violet"`
- Mega Evolution era base config owns: `ERA = "Mega Evolution"`
- Scarlet & Violet set configs inherit ERA from that era base config by default
- Generic/unscoped configs remain era-neutral (blank/missing ERA) so fallback
  behavior is intentional and explicit

Why this matters:
- avoids redundant per-set ERA duplication
- keeps shared era identity in the intended architectural layer
- preserves resolver/orchestrator dispatch via inherited class attributes

Resolver behavior remains unchanged:
- blank/missing ERA uses orchestrator base fallback
- inherited ERA resolves the correct era-specific builder

### Coercion logic is centralized

The canonical slot coercion rules now live in one shared module:

`backend/simulations/utils/packStateModels/packStateCoercion.py`

Both paths consume the same implementation:
- Derivation path (`derivePackStateProbabilities.py`)
- Simulation path (`monteCarloSimV2.py`)

This removes rule drift risk between derived probabilities and runtime state
resolution. Future changes to coercion behavior must be made in this shared
module, not duplicated across files.


## Era Normalization Strategy
- normalize_era_key(era_name) performs deterministic normalization:
  - lowercase
  - trim whitespace
  - replace & with and
  - replace punctuation/whitespace/hyphens with underscores
  - collapse duplicate underscores

## Assumptions
- First pass targets Scarlet & Violet pack structure:
  - 4 commons, 3 uncommons, 2 reverse-or-higher slots, 1 rare slot.
- special illustration rare and hyper rare are exclusive singleton-style outcomes for normal packs.
- illustration rare can coexist with rare/double rare/ultra rare, but not with additional reverse_1 major hits in the default conservative model.
- ace spec and pattern-style outcomes can coexist with one other major hit under the max-major-hit constraint.
- Bonus hits are treated separately from primary/exclusive hits and respect a total non-regular-slot cap of 2.

## Validation and Tracking
- Validation now checks incompatible hit pairs (IR+SIR, SIR+HR, HR+IR), exclusive singleton rules, slot completeness, and rarity pool compatibility.
- Validation emits a warning when state probabilities are highly skewed.
- God and demi-god paths now update rarity_pull_counts and rarity_value_totals so summaries reflect all pack paths.

## Extensibility Points
- Configs may define either:
  - get_pack_state_model(), or
  - PACK_STATE_MODEL.
- Configs may provide PACK_CONSTRAINTS to override major-hit limits and exclusivity behavior.
- Configs may provide get_pack_state_overrides() to apply set-level deltas on top of era defaults.
- Era defaults live outside the simulator in dedicated builders (Scarlet & Violet implemented first).
- Future era builders should be added in backend/simulations/utils/packStateModels/ using the naming convention above.

## Set Override Pattern (Phase 4)
- Pattern: era = default truth, set = delta.
- Scarlet & Violet builder now applies get_pack_state_overrides() via merge_pack_state_models(base_model, overrides).
- Merge strategy:
  - state_probabilities: override/add keys, then normalize to sum=1
  - state_outcomes: merge per state, allow new states, require complete slot definitions
  - constraints: union set-like hit categories and override scalar limits
- This avoids duplicating full era models in each set config and keeps overrides composable and minimal.
- Implemented override examples:
  - Prismatic Evolutions: pattern/ace deltas and additional pattern state
  - Black Bolt / White Flare: black white rare in rare-slot state
  - Ascended Heroes / Mega Evolution: reverse_1 high-rarity placement and mega hyper exclusivity delta

## Integration and Safety
- Existing backend/simulations/monteCarloSim.py is unchanged.
- Existing flow remains intact and defaults to V1.
- V2 is opt-in behind config flag USE_MONTE_CARLO_V2 (default False in BaseSetConfig).
- Main entrypoint path through main_refactored.py and calculate_pack_simulations(...) remains unchanged.

## TODOs / Uncertainties
- Scarlet & Violet default state probabilities remain provisional and require calibration against observed pull data.
- Per-set official state models may differ from era defaults; PACK_STATE_MODEL should be supplied when set-specific pack composition is confirmed.
- Special-pack fixed-card lookup currently assumes card names are present in the working DataFrame; missing names degrade tracked value/count fidelity.
