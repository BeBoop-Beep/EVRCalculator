# Rankings follow-up B6 final acceptance

Date: 2026-10-01

Branch: `fix/rankings-followup-integrated-acceptance-b6-20261001`

Starting candidate: `08c32d35c0a2b34282eea9667cb6f3f80cf321f6`

## Verdict

`READY_FOR_DEVELOP_REVIEW`

No application-code correction was required. The exact B5 candidate passed the
cross-bucket source audit, 137 focused backend tests, 113 focused frontend
tests, the controlled Product and Card production-browser certifications, and
an optimized Next production build. The full frontend result improved from the
recorded B5 baseline by one failure; no failure is a Rankings follow-up
regression.

## Integrated contract result

| Bucket | Result | Integrated evidence |
| --- | --- | --- |
| B1 | PASS | Benchmark neutral band and percentile contracts pass; tier-driven borders and shared green/white selected states remain in source and focused tests. No production caller invokes `public_rank_tier`; no blanket purple-border implementation was found. |
| B2 | PASS | Era/Set use one score table, canonical per-metric ranks, local sort/search without rank recomputation, one public read plus at most one paid wide read, and a separate Pack Economics view. |
| B3 | PASS | Overall permanence, Clear All, persistent/hover focus, large scrollable tooltip, request-free display interactions, range isolation, prewarm/dedupe, and identity-scoped history cache all pass focused tests. Established production-browser evidence is retained in this B6 evidence set. |
| B4 | PASS | Relational paid authority, server pagination/sort, scalar Chase, Collector Appeal wording, exact-SKU Recover Cost, adaptive precision, page-first Economics enrichment, Best-Open, and identity-only public catalogue all passed the B6 production-browser run. |
| B5 | PASS | Truthful cold loading, one Cards chunk boundary, entitlement-gated prewarm, conditional enrichment, narrow Chase projection, global component ranks, and session cache passed focused and B6 browser certification. |

## Access and safety

| Viewer | Result |
| --- | --- |
| Anonymous | PASS: public Overview and Overall headlines; identity-only Product catalogue; protected history/metrics/Cards locked; public response and rendered-attribute scans found no protected keys. |
| Base | PASS: contract and browser request audit show no paid Card request; protected surfaces remain locked. |
| Plus | PASS: wide Era/Set metrics, Product Scores/Economics, Financial history, and Collector Cards are enabled; Premium Chase remains unavailable. |
| Premium | PASS: Plus behavior plus Chase Efficiency; Collector remains warm when returning from Chase. |

`MID_SESSION_BROWSER_ACCESS_BLOCKED`: the static fixture harness cannot safely
change the authenticated plan while requests are in flight. This is not left
unproved: focused contracts verify PLUS -> BASE removes paid Era/Set cells,
Product/Card/history data is identity-scoped, late results are discarded, and
PREMIUM -> PLUS removes Chase while preserving Plus capability.

`LIVE_DB_ACCEPTANCE_BLOCKED`: no legitimate Supabase URL/service credentials
were present. No database connection or mutation was attempted. B6 relies on
the recorded B0-B5 live evidence for the 22 Sets, 2 Eras, 138 Products, 18,293
Collector rows, and prepared Chase authority.

## Browser, mobile, and accessibility

The controlled production build was exercised in fresh Chromium contexts.
Desktop and mobile evidence covers Overview/graph, unified Era/Set surfaces,
both Product views, both Card views, pagination/filter controls, and a mobile
Rankings graph. Active controls retain green/white state. Focus and Clear All
are display-only; Overall remains after Clear All. Public surfaces remained
locked without data leakage.

Focused contracts verify `aria-checked`/`aria-pressed`, `aria-sort`, the Clear
All name, separate legend Focus/remove controls, keyboard/touch tooltip access,
Best-Open interaction, accessible pagination, useful Card loading copy, and
non-color rank/lock information. No major mobile overflow regression was seen.

## Test and build summary

- Backend focused: **137 passed**, 0 failed.
- Frontend focused: **113 passed**, 0 failed.
- Full frontend: **3,586 total; 3,253 passed; 299 failed; 34 skipped**.
- Failure classification: **0 FOLLOWUP_REGRESSION**; the 299 failures are
  `PRE_EXISTING_BASELINE` or `UNRELATED_CURRENT_DEVELOP_DRIFT`. This is one
  fewer failure than the recorded B5 baseline (3,252 pass / 300 fail / 34 skip).
- Production build: optimized compile PASS; lint/type completed with known
  unrelated warnings; page data PASS; static generation **85/85**.
- `/Rankings` First Load JS: **119 kB**, unchanged from B5.

No migration, publication, production write, deployment, merge, or push was
performed.
