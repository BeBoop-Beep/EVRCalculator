# B6 regression matrix

| Area | Acceptance | Result |
| --- | --- | --- |
| Branch integrity | Exact B5 SHA; all B1-B5 commits ancestral; no merge/rebase | PASS |
| Tier authority | 4.75-5.25 inclusive benchmark C; above/below rules; Product/Card percentile tiers | PASS |
| Selected states | Rankings active surfaces green/teal with white wording | PASS |
| Era/Set | Unified tables; canonical rank sort; public/paid split; separate Pack Economics | PASS |
| Graph | Overall permanent; Clear All; persistent/hover focus; scrollable tooltip; isolated cache | PASS |
| Product | Relational authority; bounded paging; scalar Chase; exact recovery; page-first enrichment | PASS |
| Cards | Plus Collector; Premium Chase; global ranks; truthful cold state; one async boundary | PASS |
| Request architecture | One public + max one paid Era/Set read; paged Product reads; one Card row + facet; warm dedupe | PASS |
| Payload safety | Public Product identity-only; public headlines Overall-only; zero Base Card requests; response/DOM key scan | PASS |
| Anonymous/Base | Public data only; protected surfaces locked | PASS |
| Plus | Wide metrics, Product, Collector, and history; no Chase | PASS |
| Premium | Plus plus Chase Efficiency | PASS |
| Mid-session browser transition | Harness cannot mutate authenticated plan safely | `MID_SESSION_BROWSER_ACCESS_BLOCKED`; focused contracts PASS |
| Live read-only database sanity | No legitimate credentials available | `LIVE_DB_ACCEPTANCE_BLOCKED`; prior evidence retained |
| Desktop/mobile | Representative production-browser evidence; controls remain usable | PASS |
| Accessibility | aria states/sort, separate legend controls, named Clear All, keyboard popover, semantic loading/locks | PASS |
| Backend focused | 137 pass / 0 fail | PASS |
| Frontend focused | 113 pass / 0 fail | PASS |
| Full frontend | 3,253 pass / 299 fail / 34 skip, 3,586 total | 0 follow-up regressions; baseline/drift only |
| Production build | optimized build; lint/type; data; 85/85 static pages | PASS |
| Bundle | `/Rankings` 119 kB vs B5 119 kB | PASS |
| Source hygiene | No paid-v2 snapshot dependency, direct legacy tier caller, nested Card child chunk, or Product legacy labels | PASS |

## Failure classification

The full suite is a repository-wide drift detector, not a green baseline. Its
299 failures include stale SEO/Explore source-string expectations and unrelated
Market Explorer contracts. The exact focused B1-B5 set is green (113/113), the
backend redesign/service set is green (137/137), and controlled browser suites
are green. Therefore:

- `FOLLOWUP_REGRESSION`: **0**
- `PRE_EXISTING_BASELINE` + `UNRELATED_CURRENT_DEVELOP_DRIFT`: **299**

This run is slightly better than the recorded B5 baseline of 300 failures; B6
did not modify application code or opportunistically repair unrelated tests.
