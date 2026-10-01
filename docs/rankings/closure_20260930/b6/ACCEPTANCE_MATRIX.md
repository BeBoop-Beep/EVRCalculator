# Bucket 6 acceptance matrix

| Requirement | Status | Evidence |
|---|---|---|
| R33 Product interaction performance | PARTIAL / runtime blocked | Separate endpoints and warm cache verified; 70-test suite green; cold authenticated production measurement blocked. |
| R34 remove Cards outer selector chrome | PASS | Selector is now a plain workspace control; data surfaces remain. |
| R35 preserve Card lenses/filters/ranks/access | PASS | Five lenses, shared filters, plan gates, pagination, images/links, and backend global-rank contract retained. |
| R36 login to Cards without refresh | SOURCE/FIXTURE PASS; live blocked | Resolving state, identity remount, entitlement transition, generation checks, and Retry implemented; authenticated browser unavailable. |
| R37 Card interaction performance | PARTIAL / runtime blocked | Immediate feedback, keyed cache reuse, no non-search debounce, and bounded reads proved; live latency unavailable. |
| R39 logout/downgrade safety | PASS (deterministic) | Paid state clears, generation invalidates, identity changes isolate cache; B1 Product purge contract remains green. |
| R40 races and last-good | PASS (deterministic) | Latest generation wins; forced cache successor wins; same-query last-good survives labeled refresh failure; new query clears old rows. |
| B1 public/access contracts | PASS | Included in 70/70 frontend run. |
| B2 presentation/artwork/neutral controls | PASS | Included in 70/70 frontend run. |
| B3 exact-SKU economics | PASS | Included in 70/70 frontend run. |
| B4 absolute Product/reference/Best-Open | PASS | Included in 70/70 frontend run. |
| B5 history contract | PASS | Included in 70/70 frontend run. |
| Backend unit execution | BLOCKED | Supabase variables absent; pytest stopped during collection. |
| Authenticated browser | BLOCKED | No legitimate test session. |
| Live read-only DB performance | BLOCKED | No authorized configured connection. |
| Production build/browser | BLOCKED | `BACKEND_API_BASE_URL` absent. |

Global-rank proof: the unchanged service calls `get_pokemon_card_component_rankings_v1`, applies display filters through that global-cohort authority, returns `rankSemantics: global_component_cohort`, and enriches only `ranking_rows`. No frontend re-ranking exists.
