# Rankings parallel-agent reconciliation audit

Date: 2026-09-30  
Repository: `D:\EVRCalculator`

## Result

Canonical B1 is intact at `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4`. No duplicate or divergent B1/B2 branch or commit descended from B0 was found. B2 did not proceed because unrelated source files began changing during the audit and the shared frontend dependency tree is both incomplete and held open by an active Next development server.

## Recorded state

- Initial working directory: `D:\EVRCalculator`
- Initial branch: `fix/rankings-public-access-b1-20260930`
- Initial HEAD: `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4`
- B0: `e231a7dad56c42ad4418dc54cd135be5859fed06`
- Historical source: `80ed964161a3600d900624da6155a63b91962d74`
- `origin/develop`: `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9`

Initial status contained only the three protected unrelated paths:

- `logs/run_simulations.log` modified
- `logs/task_scheduler_debug.log` modified
- `docs/research/market_activity_v1/FMA5_RELEASE_HANDOFF.md` untracked

## Relevant branches and worktrees

| Branch | Worktree | SHA | Relationship/classification |
|---|---|---|---|
| `audit/rankings-closure-b0-20260930` | `D:/EVRCalculator-rankings-b0-audit` | `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9` | Historical B0 audit worktree; clean; F (`UNRELATED_WORK`) relative to the local B0/B1 continuation because it remains at origin/develop. |
| `audit/rankings-closure-b0-local-20260930` | none | `e231a7dad56c42ad4418dc54cd135be5859fed06` | Local B0 baseline; merge-base with B1 is itself. |
| `fix/rankings-public-access-b1-20260930` | `D:/EVRCalculator` | `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4` | A (`IDENTICAL_B1`); exact intended commit and only branch descended from local B0. |

Older `feat/rankings-redesign-*`, `fix/rankings-redesign-final-acceptance-20260929`, and `rankings-repair-release` worktrees predate this closure lineage and are F (`UNRELATED_WORK`) for the parallel B1/B2 incident. No branch named `fix/rankings-shared-presentation-b2-20260930` or reconciled equivalent exists.

## Divergence proof

The only local heads for which B0 `e231a7d` is an ancestor were:

- `audit/rankings-closure-b0-local-20260930` at B0 itself;
- `fix/rankings-public-access-b1-20260930` at intended B1.

For intended B1:

- merge-base with B0: `e231a7dad56c42ad4418dc54cd135be5859fed06`
- merge-base with intended B1: `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4`
- unique commit: `b9909b14 Implement Rankings public access contracts`
- tree: `c4a5d00f616faee27484016f63c0f2076bee08d3`
- B0-to-B1 delta: 23 files, 567 insertions, 68 deletions

No alternative descended commit was available for patch-id/tree comparison. `git fsck --no-reflogs --unreachable` found no unreachable Rankings/Bucket/public-access/presentation/closure commit. The reflog shows the intended B1 commit and an earlier reset to B0, but no second B1 or B2 commit.

## B1 integrity

Tree inspection confirms the commit contains:

- public Era and Set Overall headline readers and proxies;
- narrow public Set Pack Economics preview;
- independently sourced, paginated, alphabetical Product catalogue;
- retained paid scorecard, detailed economics, and Product analytics gates;
- Product and Set paid-state clearing on entitlement loss;
- B1 implementation, acceptance, and security documents;
- focused backend/frontend contracts and browser smoke harness.

Fast backend integrity tests were started against the exact source and reached the test completion line. Existing prior B1 evidence remains 30/30 backend and 64/64 frontend. Frontend checks were not rerun in this audit because the dependency tree is unsafe.

## Unexpected concurrent source changes

During the audit, after the initial clean-source status was recorded, another process/agent created these additional changes:

- `frontend/components/explore/MarketExplorerClient.jsx` — modified; 58-line mobile controls/dialog/focus-management change; unrelated Market Explorer work.
- `frontend/components/explore/MarketExplorerConstituents.jsx` — modified; mobile horizontal movement-window layout change; unrelated Market Explorer work.
- `frontend/components/explore/MarketExplorerBucket4.contract.test.mjs` — untracked; unrelated Market Explorer Bucket 4 work.

These do not overlap B1 files, but their appearance during the audit proves the shared worktree is actively being mutated. Nothing was discarded, stashed, restored, or staged. A safe attempt to create a reconciliation branch was refused by Git because switching would overwrite the concurrent Market Explorer changes; the branch was not created.

## Node modules state

Classification: `NODE_MODULES_ACTIVE_LOCK` and `ENVIRONMENT_BLOCKED`.

Observed active processes:

- npm `run dev` PID 35184
- Next dev CLI PID 18360
- Next start-server PID 27312

Observed dependency state:

- `frontend/node_modules/next/package.json`: missing
- `frontend/node_modules/next/dist/bin/next`: missing
- `frontend/node_modules/typescript/package.json`: missing
- `frontend/node_modules/react/package.json`: present
- `frontend/package-lock.json`: present

The active Next development processes hold the same package tree involved in the earlier `EPERM` failures. They were not killed, and no dependency repair was attempted during this audit.

## Decision

- Canonical continuation commit: `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4`.
- No duplicate branch should be merged or cherry-picked.
- No unique B2 work was found to reuse.
- B2 was intentionally not started.
- Before B2, the owner of the active Market Explorer/dev-server work must finish or move it to its own worktree and release `frontend/node_modules`. Then restore dependencies from the existing lockfile without changing manifests and create `fix/rankings-shared-presentation-b2-20260930` from exact canonical B1.

B4 remains pending and out of scope: `B4_PENDING_PRODUCT_SCORE_REFERENCE`.
