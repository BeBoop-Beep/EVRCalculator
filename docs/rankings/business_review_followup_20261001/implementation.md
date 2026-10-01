# Rankings business-review follow-up

Implemented on `fix/rankings-business-review-followup-20261001` from `origin/develop` at `34713809dab4100a61f80fb957d8fb461f106cf0`. The accepted implementation commit is `664ba13f`.

## Delivered contract

- Product intent and idle prewarming share the session cache and keep public and entitled reads separate.
- Full Market Product Scores and Economics require Index Premium. A supported family requires Index Plus. Both API paths enforce the same scope rule.
- The public Product catalogue is projected from the current ranked authority, so unsupported or unrankable inventory is not disclosed.
- Set and Era score cells retain their numeric score and expose canonical rank and percentile tier. Collector and Chase are cohort-relative 0–10 presentation values; their tiers come from canonical rank percentiles and they have no universal 5.0 reference.
- Era Collector and Chase values are equal-Set aggregates of Set presentation values. This is presentation only and does not alter a published model, rank, or tier.
- The reference row remains 5.0 only for Overall and Financial. Collector and Chase show an explained em dash.
- Pack Economics uses `Packs`; Set parents say `Varies`, while expanded exact Products show their pack counts.
- History controls include 1D and 7D, Era preset selection is single-valued, and the permanent Overall line/key is white and dashed.

No migration, index, publication, deployment, production write, or model recalculation was performed.

## Final closure — 2026-10-01

### Production build

The production build used the established local placeholder procedure with both `BACKEND_API_BASE_URL` and `NEXT_PUBLIC_BACKEND_API_BASE_URL` set to `http://127.0.0.1:8001`; no `.env` file was changed. Optimized compilation, lint/type checking, page-data collection, and static generation all completed. The build generated 86/86 static pages. `/Rankings` reports 120 kB First Load JS, one kilobyte above the 119 kB B5/B6 baseline. Known unrelated lint warnings and backend-unavailable/dynamic notices remained in the previously accepted class.

### Controlled browser acceptance

Acceptance ran against the production server using Playwright route interception on the application's normal `/api/auth/me`, public Rankings, and paid Rankings paths. A local read-only HTTP fixture supplied only SSR overview/cohort data. It supported Anonymous, Base, Plus, and Premium identities without an auth bypass or production contact.

| Identity | Full Market Products | Supported family | Observed paid requests |
| --- | --- | --- | --- |
| Anonymous | centered Premium lock | centered Plus lock | 0 |
| Base | centered Premium lock | centered Plus lock | 0 |
| Plus | denied | Scores and Economics available | 1 Scores + 1 Economics |
| Premium | Scores and Economics available | inherited | 1 Scores + 1 Economics |

Anonymous and Base showed no wall of locked rows. The public family authority exposed only Booster Box, Booster Bundle, Elite Trainer Box, Pokémon Center Elite Trainer Box, Booster Pack, Sleeved Booster Pack, Half Booster Box, and Enhanced Booster Box; unsupported catalogue-only families were absent. Direct backend tests prove Plus unscoped access is 403 while Premium unscoped and family access succeed.

Response, rendered text, ARIA, and data-attribute scans found no protected Product values for Anonymous/Base. Existing Card and Era/Set entitlement boundaries remained covered by focused contracts and the controlled fixture.

### Scorecards and Pack Economics

Desktop and mobile browser evidence confirms the reference row's rank dot is aligned with the Rank column, `Pokémon Overall Average` is in Entity, and only RIP Score and Financial show 5.0. Collector and Chase show informational unavailable states. Real cells display score plus canonical `#rank [tier]`; no browser-side rank is calculated.

The two Era Collector fixtures remain close (7.9 and 7.9 after display rounding), while Chase remains separated (8.8 versus 7.6), proving there is no forced two-Era 10-to-0 normalization. Era Pack Economics says `Pokémon Overall`, not `All modeled sets`. Set Pack Economics has `Set / Product`, `Packs`, and `Products`, no Families column or raw family key. Its parent says `Varies`; expanded exact Products show pack counts 1, 6, 9, 11, and 36.

### Era presets and Financial history

The controlled browser selected Scarlet & Violet and then replaced it with Mega Evolution; the closed selector summary and plotted selection both showed only Mega Evolution. A deterministic regression exercises Scarlet & Violet → Mega Evolution, Mega Evolution → Scarlet & Violet, and empty/manual state.

The production fixture displays all seven controls: 1D, 7D, 30D, 3M, 6M, 1Y, and ALL. Model tests prove 1D uses the active end date, 7D includes that date plus the preceding six calendar days, gaps are not interpolated, and Overall-only requests retain a transport-only anchor across ranges. The Overall line and legend sample are bright near-white and dashed; entity lines are solid. The selected window uses the shared teal/green surface with white text and retains focus-visible styling.

### Performance evidence

Local development timing was separated from production health:

- Product endpoint, first development hit: 4.810 s total, including a 1.893 s route compile; immediate repeat: 0.037 s.
- Card Collector endpoint, first observed hit: 0.375 s total, including a 0.277 s route compile; immediate repeat: 0.037 s.
- Card component lens after the shared Card route compiled: 0.035 s; immediate repeat: 0.037 s.
- Controlled Product intent/click: Premium issued one Scores request; Plus issued one family Scores request. Mount joined the prewarm/session-cache authority with no duplicate.
- Existing focused cache contracts prove the equivalent Collector prewarm/mount join and isolate component-lens request identities.

These are local development observations, not production latency claims. Next development JIT compilation was not eliminated. The production browser fixture remained healthy and rendered the accepted views.

### Automated verification

- Backend closure subset: 135 passed. This includes Product access/boundaries, Product ranking contracts, scorecards, Pack Economics, and paid-response behavior.
- Focused changed-path frontend subset: 64 passed, including the new bidirectional preset test, Product layout/access, Pack Economics, Financial history, Overall-only transport, and plan inheritance.
- Full frontend repository suite: 3,263 passed, 307 failed, 34 skipped. This improves on the accepted integrated baseline of 3,191 passed, 322 failed, 34 skipped. Remaining failures are pre-existing or unrelated develop source-shape drift; no business-review regression remains.
- Controlled production-browser harness: PASS for all four identities, lock matrix, supported-family boundary, paid Product reads, scorecards, Packs, reverse Era replacement, ranges, dashed Overall, selected-button styling, and leak scans.

Closure required no production source fix. Two backend tests were updated for the merged publication-authority seam, the Premium feature-count expectation was reconciled, and the explicit bidirectional Era preset regression was added.

### Evidence

Evidence is stored in `docs/rankings/business_review_followup_20261001/evidence/`, including:

- `anonymous-product-all-lock.png`
- `anonymous-product-family-lock.png`
- `plus-product-authorized.png`
- `premium-product-authorized.png`
- `era-score-table.png`
- `set-score-table.png`
- `era-pack-economics.png`
- `set-pack-economics-expanded.png`
- `financial-graph-ranges-overall.png`
- `era-preset-reverse-replacement.png`
- `score-table-mobile.png`

No live database, production authentication, or production service was needed or contacted. Those environments remain intentionally outside this closure; they do not block code readiness because all requested business-review behavior is certified with current-contract controlled fixtures and deterministic tests.
