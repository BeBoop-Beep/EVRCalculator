# ACTIVE database incident — 2026-09-25 Phoenix

Status: CONTAINED, recurring workload NOT yet certified for restart.

## Verified recurrence evidence

At the initial 2026-09-26 03:17 UTC VM audit, all 14 application cron entries had been restored (zero CODE_RED_DISABLED entries), and a snapshot wrapper plus refresh child were running. Run 36214342233, job 108327202787. We have not attributed the restoration to a particular chat or person.

The 00:15–03:16 UTC edge-log window contained 70,890 events and 259 responses with status >=500. Python maintenance traffic dominated. PostgreSQL logs contained 18 database-interruption records between 00:09 and 02:47 UTC. These are restart/recovery symptoms, not proof of an OOM kill.

Supabase emailed a warning at 2026-09-25 04:45:45 UTC that TheIndex was running out of disk IO budget. The warning is not a measured claim that budget reached 100% during every interruption.

The initial resource sample had approximately 212 MiB available RAM, 627 MiB used swap, and memory commitment approximately 124% of the reported commit limit on Micro. Free data disk space was approximately 10 GiB. Cumulative swap occupancy is not an instantaneous swapping rate. The post-containment current-host OOM-kill counter was zero; historical host/kernel OOM causality remains unproven.

Timeout signatures included full Cards snapshot payload_json plus cards_json, and full Set Page payload/title/summary JSON reads. The pre-launch trigger used the legacy core audit despite an existing metadata-first compact runtime adapter.

## Executed containment

1. Re-ran code-red-db-load-shed (operational commit 40e1dadac60817a6878225e756989ac8e53e0010).
2. Installed host-local maintenance admission control from vm-ops-control, run 36214735136 / job 108328349527. All 19 tests passed.
3. Live application cron entries remain disabled. Their canonical restore backup now contains guarded commands. The old unwrapped backup and pre-install crontab are preserved as timestamped, mode-600 files under /home/ubuntu/state/db-safety.
4. Persistent HOLD: /home/ubuntu/state/db-safety/hold.json. Runtime guard: /home/ubuntu/state/db-safety/db_workload_guard.py. State is outside Git; ordinary checkout/sync cannot clear it. No automatic release on a green health probe.
5. Guarded commands have single-command host admission, per-command failure cooldowns, and conservative memory/swap/commitment preflight and runtime trip conditions. Missing metrics fails closed. These thresholds are engineering containment settings, not vendor-certified capacity limits.
6. Verified HOLD blocks execution without contacting the DB; remaining known VM workers were absent. No business-data deletion, restore, compute upgrade, or database restart was performed by this incident pass.

## Targeted source repair deployed

PR #382: fix/production-db-safety-hold-20260925; source 898fe31540a1c40a2d34d29eb3629c361b3250bc, based on main 0ca31bab086f63f48b472d8119741619ad43d7ee.
Production local overlay: 087b30a7efabee9474b170cc6b4e8a2d95e9c41f.
Controlled run 36215140030 / job 108329510003 passed.

- Gate canonical publication before projection/currency DB reads, before detached launch, and in the shell wrapper itself.
- Default currency check now calls the existing compact/resilient audit instead of the legacy oversized JSON reader.
- Failed lightweight source-date check returns UNKNOWN instead of escalating to heavier work.
- 11 new tests plus the complete 23 existing trigger tests passed. Existing fixtures were corrected to supply explicit readable scalar authority when testing later verdict stages. Verdict assertions were retained.
- Live wrapper returned 75 and trigger returned skipped_database_safety_hold; no publication launched.
- Python compile, shell syntax and diff checks passed.

## Latest verified service state

At 03:25:40 UTC: REST read 200 (~113 ms), Auth health 200 (~117 ms), Storage metadata 200 (~251 ms). Available RAM ~482 MiB; swap still ~550 MiB. These are small smoke checks, not full user-flow tests or capacity certification.

At 03:33:12 UTC: PostgreSQL start time remained 03:13:59 UTC, in_recovery=false, 9 client connections, no other active queries, archival failure counter zero since its latest reset. Database-native price-storage-v2-shadow-cycle (job 19) remains inactive.

## Required recovery boundary

Do not remove HOLD or restore bulk work merely because the dashboard is green. The application is intentionally trading background freshness for availability while the recurring workload is repaired and validated. Do not erase the existing vintage/Explorer changes.

These controls are NOT a distributed queue or authorization boundary. Direct MCP SQL, Windows-run jobs, unwrapped scripts and independently detached processes can bypass the host-local command guard. Keep expensive production work in other chats paused; offline implementation/tests may continue. All such entrypoints must be brought under coordinated admission before certifying safe overlap.

Next: preserve PR #382 in canonical main, obtain appropriate compute headroom (Small is a reasonable immediate step, not proven sufficient), audit the remaining recurring rebuild/JSON-read and simulator-persistence paths, and reintroduce bounded workloads one at a time. A controlled workload test and longer observation are still required. Escalate recurring interruptions under low load to Supabase with timestamps and resource evidence. No support request has been submitted by this pass.
