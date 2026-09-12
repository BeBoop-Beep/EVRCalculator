# Overall RIP versioned-publication dependency map

## Authority flow

`simulation_sealed_product_results` component payloads → weighted Overall calculation →
`pokemon_overall_rip_publication_runs` + `pokemon_overall_rip_publication_rows` →
rank/tier in the same immutable row → separate version-bound `rankings` and `set_page`
generations → one `pokemon_overall_rip_current_publication` pointer →
`pokemon_overall_rip_active_v` → `overall_versioned_publication_service` stable projection.

## Reader/write-path classification

| Class | Path | Finding |
|---|---|---|
| A — generic/version-aware | `backend/desirability/overall_versioned_publication.py` | Model-number-independent rank, tier, validation, and projection contract. |
| A — generic/version-aware | `backend/db/services/overall_versioned_publication_service.py` | Reads only the atomic active view and rejects mixed authority IDs. |
| A — generic/version-aware | `pokemon_overall_rip_active_v` | Resolves the explicit pointer; never resolves “latest.” Service-role only during transition. |
| B — adaptable V12-specific | `backend/db/services/product_family_rankings_service.py`, `public_overall_product_rankings_service.py`, `budget_product_ranking_service.py` | Current public rankings derive generic-looking fields from V12-specific snapshot columns/flags. Route through the new service before V13 promotion. |
| B — adaptable V12-specific | `backend/db/services/pokemon_sealed_product_detail_service.py`, `pokemon_public_snapshot_service.py`, `set_rip_service.py` | Current detail/set-page payloads consume the legacy snapshot generation. Route Overall fields through the new active projection while retaining standalone Collector fields. |
| B — adaptable V12-specific | `backend/api/main.py`, `backend/domain/access/index_plan_access.py` | API and entitlement projection can retain stable public names once their upstream services use the generic reader. |
| C — activation blocker | Running production deployment | It has not shipped the generic service/view consumption; therefore V13 must remain inactive. |
| D — historical-only | `pokemon_public_rip_leaderboard_history` and temporal-authority migration `20260911213011` | Existing V12 history is immutable. New generic history must be keyed by publication run/model version from activation forward; no V13 backcast. |
| E — unused/legacy | Old V5–V11 calculation/migration contracts | Retained for audit and compatibility; not current authority. |

## Original blockers closed

- Generic append-only runs and rows replace the need for a V13 column family.
- Score, rank, tier, eligibility, components, and lineage share one publication-row key.
- Rankings and set-page artifacts are distinct generations bound to one run.
- The singleton pointer holds the run and both generation IDs and is switched by one RPC transaction.
- Prior runs and generations remain immutable rollback targets.
- Existing V12 columns, snapshots, RPCs, and historical rows are untouched.

The only activation blocker is the intentionally prohibited application deployment: running readers are still in class B/C.
