# Market Explorer review closure — 2026-10-02

## Scope and release state

- Starting authority: `origin/develop` at `e49635974ce8f60820f132d0d0c876f39ae1da9f`.
- Branch: `fix/market-explorer-review-closure-20261002`.
- This pass did not merge, deploy, promote a migration, write production data, or call a pricing provider.
- Production Explorer cache receipt is `CURRENT`: canonical accepted date `2026-10-01`, V2 surface date `2026-10-01`, lag `0`, maintained markets `37/37`, and no alert reasons.

## Closure matrix and root causes

| Area | Root cause | Closure |
|---|---|---|
| Normal chart controls | Performance was still exposed as a peer view despite Index being the authoritative normal graph. | Normal control is Index-only; Market Activity remains a distinct capability-gated action. Existing performance calculations were retained. |
| One-year chart | The fixed 365-day domain reserved empty calendar space before the earliest available observation. | The 1Y start is `max(end - 365 days, earliest drawable observation)` so available history occupies the full plot. |
| Active-market chips | Focus was confined to a small icon and selector rows did not deselect already-active markets. | Any chip area except visibility/remove focuses; a second focus click clears; X removes only; active directory rows deselect. Parent Raw Card and Total Sealed markets use the same path. |
| Constituents | Page one began only when the detail panel opened. | Focus now prefetches page one through the existing generation-pinned cursor cache; subsequent pages retain `afterRank` paging and the detail fallback remains the first active market. |
| Exact/custom movement | Exact-basket item payloads lacked movement even though authoritative observation history existed. | Existing authoritative constituent enrichment is used for cards and sealed, with absent history remaining `null`; UI consumes the supplied movement fields. |
| General search | UI used the physical-leaf endpoint, so the healthy catalog RPC's prepared/set results could never render. | General search uses catalog search, normalizes RPC snake_case, groups prepared markets first, labels them with asset identity, and retains relevance ordering for leaves because the contract does not publish a sortable current-value field. Debounce, abort, and request-token stale-response protection remain in place. |
| Exact search/native popup | The browser could still infer saved-input behavior. | The input explicitly disables autocomplete/autocorrect/spellcheck and uses a non-identity field name; first-page bounds and concurrent cancellation are preserved. |
| Performance screens | RPC ranked and limited the global population before applying the requested asset. | Identical backend/Supabase migration copies filter asset inside the ranked CTE before `row_number()` and limit. The migration contract covers cards, sealed, graded, all, top/worst, and limits 1–25. |
| Tooltip completeness | Cross-series alignment required an observation on the exact shared point, yielding `—` despite an authoritative earlier observation. | Tooltip values use the nearest authoritative observation at or before the inspected date and never backfill before a line's first point. |
| Labels and polish | Generic markets could omit asset identity and remove controls lacked the comparison-pill visual language. | Prepared search labels include Cards/Sealed/Graded; exact-market remove X uses the smaller teal treatment; secondary edit actions remain neutral and Update remains primary. |

## Migration parity

The following files are byte-identical and regression-tested:

- `backend/db/migrations/20261002044542_fix_market_explorer_performance_screen_asset_ranking_20261002.sql`
- `supabase/migrations/20261002044542_fix_market_explorer_performance_screen_asset_ranking_20261002.sql`

Production had already received this migration before this branch. This branch only restores repository parity; it did not apply or promote it.

## Sealed pricing audit

Read-only production evidence:

| Family | Products | Currently fresh priced | Latest observation |
|---|---:|---:|---|
| `first_partner_pack` | 8 | 0 | 2026-08-02 |
| `world_championship_deck` | 25 | 0 | 2026-08-02 |

Both families have configured TCGplayer sealed identities/mappings and no Explorer-side family allowlist excludes them. Explorer derives availability from canonical current sealed metadata/observations. The evidence therefore points to an upstream catalog/provider refresh-coverage gap, not an Explorer classification or scope bug. No synthetic prices were created and the stale families were not hidden. Provider-side availability must be investigated through the separately authorized ingestion/provider workflow.

## Verification

- Focused backend/API/DB: **13 passed, 1 skipped**.
- Focused Explorer regression aggregate: **179 total; 145 passed, 34 intentional skips, 0 failed**.
- Final search/chart/picker slice: **38 passed, 0 failed**.
- Broader Market Explorer diagnostic: **639 total; 587 passed, 34 skipped, 18 failed**. The remaining failures are older source-text/structure assertions outside this closure; the focused behavior suites above are green.
- Repository-wide frontend diagnostic: **3606 total; 3259 passed, 34 skipped, 313 failed**. This suite has substantial pre-existing source-contract failures and is not a release-green signal; no claim to the contrary is made.
- Playwright Activity acceptance: **2 passed, 0 failed**. It covers synchronized tooltip/crosshair, Escape clearing inspection, and overflow/readability at `1728x1000`, `1440x900`, `1280x720`, `1024x768`, `834x1194`, `768x1024`, `412x915`, `390x844`, and `844x390`.
- Optimized Next production build: **passed**. Existing non-fatal lint/accessibility warnings remain.
- `git diff --check` is clean for closure files. The unrelated simulation and scheduler logs retain their pre-existing whitespace and are excluded from the commit.

## Remaining issues and recommendation

The requested Explorer closure is suitable for code review and merge once CI agrees with the focused evidence. The production cache itself is current, so the earlier stale Explorer release blocker is no longer present. First Partner Pack and World Championship Deck pricing remain stale and should be tracked as an upstream ingestion/provider-coverage issue; do not represent them as current until authoritative prices resume. No application or migration deployment should occur from this acceptance task.
