# Market Explorer Bucket 2B.1 production apply — 2026-09-24

## Production migration

- Applied `20260924000000_prepared_constituent_authority_v1` to project `zwxzxuuawalvwioadhmf`.
- The deployed `run_market_explorer_guarded_publisher_v1(date)` was read directly from production before apply and matched the migration's preserved `already_current` wrapper body, with constituent staging as the only intended extension.
- The first manual guarded-publisher call exposed a real concurrency race: a scheduled publisher and the manual call could both observe an unstaged generation and enter staging concurrently. One caller completed while the other failed on a duplicate `(generation_id, market_key)` total row.
- Production serving data remained coherent; the successful concurrent caller staged the serving generation completely.
- Added and applied forward migration `20260924010000_serialize_prepared_constituent_staging`, which adds a generation-scoped transaction advisory lock around staging and the publisher's check-then-stage decision.
- After the forward migration, the guarded publisher returned `already_current` cleanly without restaging.

## Serving generation after apply

- generation: `60c274ea-aed6-45b5-a701-ca0d29eb5f11`
- comparison/source date: `2026-09-22`
- public Set Value market date: `2026-09-22`
- prepared directory rows for the generation: 193
- staged prepared constituent total rows: 193
- staged constituent rows: 101,034
- integrity audit: 0 markets with total/rank/identity mismatch

The earlier Sep-19 generation observed by the Bucket 2B.1 subagent had already advanced to the Sep-22 generation before the production apply.

## Live v3 constituent matrix

| Market | Availability | Total | Page 1 | Next cursor | Price as of |
|---|---:|---:|---:|---:|---|
| Base | available | 102 | 100 | 100 | 2026-09-22 |
| Jungle | available | 64 | 64 | — | 2026-09-22 |
| Fossil | available | 62 | 62 | — | 2026-09-22 |
| Team Rocket | available | 83 | 83 | — | 2026-09-22 |
| EX | available | 3,235 | 100 | 100 | 2026-09-22 |
| Rare Ultra | available | 778 | 100 | 100 | 2026-09-22 |
| Obtainable | available | 26,395 | 100 | 100 | 2026-09-22 |
| Booster Boxes | available | 54 | 54 | — | 2026-09-22 |
| Packs | available | 178 | 100 | 100 | 2026-09-22 |
| Elite Trainer Boxes | available | 77 | 77 | — | 2026-09-22 |

The Packs page-2 compact-table query used the prepared constituent primary key and returned 78 rows in ~0.96 ms execution time. It did not parse the sealed snapshot JSON or recompute the upstream roster.

## Remaining acceptance gap

Browser acceptance is still unverified in this environment. The database/runtime blocker for merging the v3 backend is removed: the v3 function and compact authority are deployed before the branch backend reaches develop.
