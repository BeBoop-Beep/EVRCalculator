# Runtime certification

## Environment

- Worktree: `D:\EVRCalculator-rankings-b7`
- Branch: `integration/rankings-closure-b7-20260930`
- Starting SHA: `86010620e588b44206fb83640ba262214e48662e`
- Date: 2026-09-30 (America/Phoenix)
- Frontend: Next.js 15.5.15, production output `.next-build-1116`
- Production server: `http://127.0.0.1:3107`
- Documented backend base: `http://127.0.0.1:8001`

## Commands and results

1. `npm.cmd run build` with only `BACKEND_API_BASE_URL=http://127.0.0.1:8001`: FAIL at `/waitlist/verify` because the client build variable was absent. This was configuration evidence, not a product defect.
2. `npm.cmd run build` with both backend variables set to the documented URL: PASS; compile 13.9 s, lint/type complete, page data complete, 85/85 static pages.
3. `npm.cmd start -- -p 3107` with `PERF_AUDIT_DIST_DIR=.next-build-1116` and both backend variables: PASS; ready in 408 ms.
4. `node .perf-audit/rankings-b1-public-access-smoke.mjs`: PASS for public Era/Set headlines, Set pack preview, alphabetical Products, and locked advanced metrics. The expected mocked anonymous `/api/auth/me` returned 401.
5. `node .perf-audit/rankings-b7-runtime-certification.mjs`: PASS on desktop/mobile controlled anonymous browser checks, screenshots, timing samples, payload sizes, and protected-key scans.
6. `agent-browser --version`: BLOCKED; executable not installed. Playwright fallback was used.

## Anonymous browser result

Controlled sanitized fixture runtime:

- Era score/rank visible publicly: PASS (7.1/10, #1).
- Set score/rank visible publicly: PASS (7.2/10, #1).
- Missing Set art falls back to initials (`AS`): PASS.
- Product catalogue is alphabetical (`Alpha Elite Trainer Box`, then `Zulu Booster Box`): PASS.
- Product family controls and Scores/Economics switch: PASS.
- Product analytics/economics values: 12 locked cells; no paid values rendered: PASS.
- Representative desktop and mobile layouts: PASS.
- Overview real Top Set/Top Era/economics data: BLOCKED_RUNTIME; four cards display “Temporarily unavailable” because no legitimate backend exists.
- Graph runtime interactions: BLOCKED_RUNTIME; live/premium history was unavailable.

This is actual production-browser behavior with controlled public fixtures, not live database evidence.

## Authenticated browser

`AUTHENTICATED_BROWSER_VERIFICATION_BLOCKED`. No approved Plus/Premium credentials, storage state, or session variables were present. Login transition, paid Product/Card lenses, Cards without refresh, logout/downgrade, and paid graph behaviors were not claimed.

## Live read-only database

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY` were absent. Therefore exact-SKU joins, representative distinct family values, live Product benchmark publication status, and Card query plans/timings remain BLOCKED. No connection was bypassed and no write was attempted.

## Runtime security

Controlled anonymous runtime inspection PASS:

- six captured public JSON responses across desktop/mobile (Era 240 B, Set 335 B, Product catalogue 342 B each) contained none of the protected serialized keys checked;
- two 43,629-byte production documents contained none of those serialized keys;
- rendered DOM attributes contained no protected field names;
- Product Scores/Economics displayed locked cells rather than numeric paid values;
- public Product membership/order came only from the catalogue fixture.

Checked serialized names: `financialRip`, `collectorAppeal`, `chaseAccessibility`, `ripScore`, `expectedValuePerPack`, `modeledReturnOnSpend`, `chanceToRecoverCost`, and `bestOpenPrice`. Labels such as “Financial” remain intentionally visible UI copy; no paid numeric value was exposed.

## Performance and graph

See `PERFORMANCE_CERTIFICATION.md`. Anonymous Product samples are fixture-backed browser samples and are not mixed with live backend/DB timings. Cards and graph measurements are BLOCKED_RUNTIME. The Overall-only window behavior remains covered by the integrated deterministic regression, but was not promoted to runtime PASS.

## Evidence

- `evidence/anonymous-desktop-overview.png`
- `evidence/anonymous-desktop-eras.png`
- `evidence/anonymous-desktop-sets.png`
- `evidence/anonymous-desktop-products.png`
- `evidence/anonymous-mobile-products.png`
- `.perf-audit/rankings-b7-runtime-certification.mjs` (sanitized measurement/reproduction harness)

## Defects and verdict

No runtime source defect was demonstrated, so no production behavior was changed. The release remains partially certified solely because legitimate paid/live access is unavailable.

`B7_RUNTIME_CERTIFICATION_PARTIAL`
