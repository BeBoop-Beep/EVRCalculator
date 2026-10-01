# Rankings follow-up release handoff

## Candidate chain

The B6 branch starts from exact B5 candidate
`08c32d35c0a2b34282eea9667cb6f3f80cf321f6`. Merge-base with
`origin/develop` is `d318ee7b913126edec657cf8da62cdf66d621b2c`.
Every commit below is an ancestor of the B6 candidate.

| Bucket | Final commits | Scope |
| --- | --- | --- |
| B1 | `bcdfc1f3`, `ddff5f02` | benchmark/absolute tiers, tier borders, green/white selected controls, closure normalization |
| B2 | `9de00997` | unified sortable Era and Set score tables with paid wide-metric merge |
| B3 | `5e3bcc10`, `80729722` | graph Clear All/focus/tooltip, history cache/prewarm, acceptance documentation |
| B4 | `2837d3ca`, `8f1f885b`, `5ca7f67b` | relational Products, pagination, exact Economics, certification and timing documentation |
| B5 | `876c853e`, `08c32d35` | Cards cold path, loading truthfulness, prewarm/cache, narrow projections, normalized evidence documentation |

## Reviewer handoff

Review B6 as an acceptance/documentation commit over the exact B5 candidate;
there are no application-code changes. The primary evidence is
`FINAL_ACCEPTANCE.md`, `REGRESSION_MATRIX.md`, `PERFORMANCE_SUMMARY.md`, and the
files under `evidence/`.

The two environmental limits are explicit and permitted by the brief:
`LIVE_DB_ACCEPTANCE_BLOCKED` (no legitimate credentials) and
`MID_SESSION_BROWSER_ACCESS_BLOCKED` (static plan fixture). Both retain the
earlier live evidence or focused contract proof; neither exposed a regression.

Safety statement: **no migration, no publication, no production write, no
deployment, no merge, and no push** occurred during B6.
