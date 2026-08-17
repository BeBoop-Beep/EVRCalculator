# Tasks 6–7 Addendum — re-audited integration surfaces

> **This addendum SUPERSEDES Tasks 6 and 7 of**
> `docs/superpowers/plans/2026-08-16-entertainment-cost-chase-economics.md`.
> Where they disagree, this document wins. The original plan's line numbers are
> stale and must not be used.

Audited at commit `2995b90` on `feature/rip-decision-layer`.

## A. Working-tree and surface audit

| Surface | Original plan said | Actual state now | Impact |
|---|---|---|---|
| `rip_decision_service.py` | modified by in-flight work, lines stale | **committed and stable**; `_product_decision_row` :167, `build_sealed_product_decision_contract` :196, `_load_run_population` :306, `build_top_chase_contract` :413, `build_rip_decision_contract` :470. Constants `INPUT_CARDS_TABLE` :78, `NEAR_MINT_PRICE_VIEW` :77 | **No conflict.** Structure matches. Task 6 proceeds as planned. |
| Timestamp helper | `_utc_now_iso` "if in globals()" conditional hack | **`utc_now_iso()` exists** at `pokemon_snapshot_builders.py:125`, public, no underscore | **Defect 1.** Use `utc_now_iso()`. Delete the conditional. |
| Snapshot persistence | raw `client.table(...).upsert(...).execute()` | **`upsert_row(client, table, row, *, on_conflict, commit)`** at :3725 — carries dry-run logging and statement-timeout retry | **Defect 2.** Raw upsert bypasses dry-run and retry. Use `upsert_row`. |
| Chase snapshot reader | add to `pokemon_public_snapshot_service.py` using `_service_client()` | `_service_client()` **does not exist**. That module reads via `public_read_client`. Migration 069 **revokes anon/authenticated** on the chase table | **Defect 3 (architectural).** A public read of a backend-only table returns nothing. See ruling below. |
| Run identity | Task 7 takes `run_id` param | `_merge_rip_decision_contract_into_set_payload` (:581) resolves it as `first_non_empty(decision_run_id, _snapshot_payload_run_id(payload))` | **Defect 4.** The chase snapshot must reuse the SAME resolved run id, never resolve its own. |
| `evPriceBasisAsOf` | sourced from `price_used_as_of` on the price view | **No such column.** `simulation_input_cards` carries **`captured_at`** (verified in `calculation_run_persistence_service.persist_simulation_inputs`) | **Defect 5 (spec gap).** Left as-is, this field is permanently `null`, violating the spec's provenance requirement. |
| Migration 069 | — | exactly one `069_*` file; the chase table is referenced nowhere else in the repo | **No conflict.** |
| Parallel work | expected churn | `911f3f0`, `5192768`, `5601397`, migrations 067/068 landed during Tasks 1–5. Working tree now clean except `cleaned_cards_debug.json` | **No conflict** with Tasks 6–7 targets. |

### Ruling: the chase reader moves out of `pokemon_public_snapshot_service.py`

Migration 069 deliberately grants the chase table to `service_role` only. The
public snapshot service is built entirely on `public_read_client`, so a reader
placed there would return zero rows for every set — silently, looking exactly
like "not built yet".

Two options were available: grant public read on the table, or put the reader
where backend reads belong. **Granting public read is rejected**: 069's whole
posture is that nothing is published until publication is a decision, the
frontend is deferred, and no consumer needs it yet.

**The read function therefore lives in `chase_economics_service.py`** — the
module that already owns this contract — and uses `create_service_role_client()`.
Build and read stay in one place, and the public module keeps its invariant that
every table it touches is publicly readable.

**Consequence: Task 7 no longer modifies `pokemon_public_snapshot_service.py`
at all.** That removes one of the two files contended with the parallel work.

---

## B. Task 6 (revised) — Entertainment Cost + unsupported products in `ripDecision`

Unchanged from the original plan **except** for the fail-closed requirement
below. `rip_decision_service.py` is stable and its structure matches what the
plan assumed.

### B1. Stage 2 inputs must FAIL CLOSED

**This also changes `chase_economics_service.pack_groups_for_product` (Task 5
code) — the fix belongs in Task 6 because both surfaces share the rule.**

Current behaviour (a Task 5 deferred minor, now promoted to a requirement): the
Stage 2 branch is taken only when **both** `guaranteed_component_market_value`
and `random_pack_count` are positive. A row with exactly one of them silently
falls through to Stage 1, dividing the **full** `expected_value` — promo
included — by the total pack count. That smears a certain component across
random packs and produces a confident wrong number with no signal.

Required behaviour:

```
both present and valid      -> Stage 2 path (existing behaviour, unchanged)
neither present             -> Stage 1 path (genuine Stage 1 product, unchanged)
exactly one present/valid   -> UNAVAILABLE. No fallback to Stage 1.
```

The unavailable reason must be the most accurate **existing** machine-readable
string. Use the existing Stage 2 vocabulary from
`backend/domain/pokemon/sealed_product_stage2_composition.py` — do not invent a
new one:

- missing/invalid `guaranteed_component_market_value` while `random_pack_count`
  is present → `guaranteed_component_market_price_unavailable`
  (`REASON_MISSING_PROMO_PRICE`)
- missing/invalid `random_pack_count` while a promo value is present →
  `unresolved_composition` (`REASON_NO_VERIFIED_COMPOSITION`)

Apply in both places:
- `chase_economics_service.pack_groups_for_product` — return `[]` plus the
  reason, so `target_chase_for_product` publishes an unavailable product block.
- `rip_decision_service` entertainment-cost attachment — emit
  `unsupported_entertainment_cost(reason, purchase_price=...)` rather than an
  available block computed on a mixed basis.

This matters now, not hypothetically: the parallel work is actively adding
Stage 2 composition rows (`5192768` added Phantasmal Flames), so half-populated
rows are a live possibility rather than a theoretical one.

**Regression tests required — BOTH permutations, not one:**

```python
def test_promo_value_without_random_pack_count_is_unavailable_not_stage1():
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": None,              # missing
        "guaranteed_component_market_value": 5.0,
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []
    assert reason == "unresolved_composition"


def test_random_pack_count_without_promo_value_is_unavailable_not_stage1():
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": 9,
        "guaranteed_component_market_value": None,   # missing
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []
    assert reason == "guaranteed_component_market_price_unavailable"


def test_genuine_stage1_product_still_uses_the_stage1_path():
    # Neither field present is NOT a mixed row - it is an ordinary booster box.
    row = {
        "sealed_product_id": "p", "product_family": "booster_box",
        "pack_count": 36, "product_market_cost": 149.99, "expected_value": 107.89,
        "random_pack_count": None, "guaranteed_component_market_value": None,
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert reason is None
    assert len(groups) == 1
    assert groups[0].expected_pack_value == pytest.approx(107.89 / 36)


def test_mixed_stage2_row_never_smears_the_promo_across_packs():
    # The specific wrong answer this rule exists to prevent: 32.0/9 = 3.556,
    # which silently includes the promo. Unavailable is the correct answer.
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": 9, "guaranteed_component_market_value": None,
    }
    groups, _ = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []
```

**Signature change:** `pack_groups_for_product` returns
`Tuple[List[PackGroup], Optional[str]]` instead of `List[PackGroup]`. Update its
three existing Task 5 call sites and the four existing Task 5 tests that unpack
it. Keep every existing assertion's meaning intact — only the unpacking changes.

---

## C. Task 7 (revised) — build, persist and read the chase snapshot

### C1. `eligibleCardCount` must be the UNCAPPED population

The builder MUST pass `eligible_card_count` explicitly from the pre-cap
population. The default in `build_chase_economics_contract` is `len(cards)`,
which is the already-capped list — omitting the argument silently publishes
"25 of 25".

```python
# Measure the eligible population BEFORE the cap, then cap.
eligible = select_chase_cards(priced_rows, denominators, price_used, limit=10**9)
cards = eligible[:resolved_limit]
...
return build_chase_economics_contract(
    cards=cards,
    product_rows=...,
    run_id=resolved_run_id,
    limit=resolved_limit,
    eligible_card_count=len(eligible),   # REQUIRED. Never omit.
)
```

**Required contract test** (the exact scenario the user specified):

```python
def test_eligible_count_is_the_uncapped_population_not_the_published_count():
    # 187 eligible cards, 25 published, eligibleCardCount must say 187.
    input_cards = [
        {"card_variant_id": f"v{i}", "effective_pull_rate": 100.0,
         "price_used": 10.0, "captured_at": "2026-08-15T06:30:00Z"}
        for i in range(187)
    ]
    priced_cards = [
        {"card_id": f"c{i}", "card_variant_id": f"v{i}", "card_name": f"Card {i}",
         "rarity_bucket": "ultra", "current_near_mint_price": float(500 - i)}
        for i in range(187)
    ]
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id="run-1",
        client=_FakeClient(input_cards, priced_cards),
        product_rows_fn=lambda **_k: _PRODUCTS,
    )
    assert payload["eligibleCardCount"] == 187
    assert len(payload["cards"]) == 25
    assert payload["publishedCardLimit"] == 25
```

Also add a guard test asserting the two numbers can differ at all — a build
where they are equal by construction would pass a weaker test vacuously.

### C2. Real provenance for `evPriceBasisAsOf` (spec gap fix)

`price_used_as_of` does not exist. The real column is
`simulation_input_cards.captured_at`, alongside `price_used` on the same row, so
it costs nothing extra to read.

Add an optional keyword to `select_chase_cards` (additive — all 20 Task 5 tests
keep passing unchanged):

```python
def select_chase_cards(
    price_rows,
    pull_denominators_by_variant_id,
    price_used_by_variant_id,
    *,
    limit=DEFAULT_PUBLISHED_CARD_LIMIT,
    price_basis_as_of_by_variant_id=None,      # NEW, defaults to {}
):
```

and populate `"evPriceBasisAsOf"` from it rather than from the nonexistent view
column. The builder's select becomes:

```python
select="card_variant_id,effective_pull_rate,price_used,captured_at",
```

**Unchanged rule:** a missing `captured_at` publishes `None`. It is never
defaulted to read time — that would assert a freshness nobody measured.

### C3. Builder — corrected

```python
CHASE_ECONOMICS_SNAPSHOT_TABLE = "pokemon_set_chase_economics_snapshot_latest"
```

- Reuse `rip_decision_service._load_run_population` with
  `rip_decision_service.INPUT_CARDS_TABLE` and
  `rip_decision_service.NEAR_MINT_PRICE_VIEW`. Both constants exist and are
  stable (:77–78).
- **Run identity:** the caller passes the SAME `decision_run_id` that
  `_merge_rip_decision_contract_into_set_payload` receives at
  `build_set_page_snapshot_row` (:1421, merge at :1487). The chase builder must
  never call `_snapshot_payload_run_id` itself or resolve a "latest" run — a
  second resolution can disagree with the page it accompanies, which is the
  exact failure the decision layer exists to prevent.
- No current run → publish an explicitly empty payload (`cards: []`,
  `sourceCalculationRunId: None`), never a historical fallback.

### C4. Persistence — use the established helper

```python
def persist_chase_economics_snapshot(*, set_id, run_id, payload, client, commit):
    row = {
        "set_id": str(set_id),
        "calculation_run_id": None if run_id is None else str(run_id),
        "payload_json": payload,
        "card_count": len(payload.get("cards") or []),
        "as_of": utc_now_iso(),
    }
    upsert_row(client, CHASE_ECONOMICS_SNAPSHOT_TABLE, row,
               on_conflict="set_id", commit=commit)
```

`upsert_row` (:3725) carries dry-run logging and statement-timeout retry; a raw
`.upsert().execute()` silently loses both, and would write during a dry run.
`utc_now_iso()` (:125) replaces the plan's conditional placeholder.

A chase-snapshot write failure must never fail the set-page build — this row is
not on the critical path. Wrap the call, re-raise transient errors via
`is_transient_data_service_error`, log and continue otherwise.

### C5. Reader — in `chase_economics_service.py`, service-role client

```python
def get_chase_economics_snapshot(set_id):
    """Read ONE set's published chase-economics contract.

    Uses a SERVICE-ROLE client, not the public read client: migration 069 grants
    this table to `service_role` only. A public-client read would return zero
    rows for every set and be indistinguishable from "not built yet".

    Lives here rather than in `pokemon_public_snapshot_service` because that
    module's invariant is that every table it touches is publicly readable.
    Publishing this contract to browsers is a deliberate future decision - a
    grant or a projected view - and is not made here.
    """
```

Return the same available/unavailable shape the plan specified. A missing row is
a real answer ("not built yet"), not an error.

**`pokemon_public_snapshot_service.py` is NOT modified by Task 7.**

---

## D. Files Tasks 6–7 will now touch

| File | Task | Change |
|---|---|---|
| `backend/db/services/rip_decision_service.py` | 6 | additive: entertainment cost per product, `unsupportedProducts`, `sealed_snapshot_fn` kwarg |
| `backend/db/services/chase_economics_service.py` | 6 & 7 | fail-closed Stage 2 + return-tuple signature; `price_basis_as_of_by_variant_id`; snapshot reader |
| `backend/scripts/pokemon_snapshot_builders.py` | 7 | additive: chase builder + persistence, wired at the existing merge point |
| `backend/tests/unit/db/services/test_rip_decision_service.py` | 6 | append |
| `backend/tests/unit/db/services/test_chase_economics_service.py` | 6 & 7 | append + update 4 unpacking sites |
| `backend/tests/unit/scripts/test_chase_economics_snapshot_build.py` | 7 | create |
| ~~`backend/db/services/pokemon_public_snapshot_service.py`~~ | — | **no longer touched** (ruling above) |

## E. Verification

Full-suite baseline: `123 failed, 4852 passed` at `2995b90`. **None are
attributable to this work** — nothing outside my own three modules imports them
(verified by grep). Tasks 6–7 must not increase that failure count; compare
against this baseline rather than expecting a green full suite.

Targeted regression for Tasks 6–7:

```
./backend/.venv/Scripts/python.exe -m pytest \
  backend/tests/unit/domain \
  backend/tests/unit/db/services/test_chase_economics_service.py \
  backend/tests/unit/db/services/test_rip_decision_service.py \
  backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py \
  backend/tests/unit/scripts/ -q
```
