# Price Storage V2 integration — draft, no production cutover

## Current milestone: live canary defect understood; forward-only date-safe v2 passes

The frozen migration-source window `20260905235956`–`20260906233651` remains fully reconciled. All **89** applied records match their original SQL checksums and the independent manifest `d988d2e6e877d3373f613d2351e86339`. The exact historical migration SQL remains unchanged and must not be replayed merely because its source files are now present.

The live Sep 6 read-only canary for **Evolving Skies**, **Crown Zenith + Galarian Gallery**, and **Celebrations + Classic Collection** showed raw-only `0`, V2-only `0`, missing prices `0`, review-required `0`, and exact scrape/shadow completion receipts for all three root universes. Accepted root candidates remained Evolving Skies `$8,305.06` / 237, Crown Zenith `$2,634.47` / 230, and Celebrations `$624.16` / 50. Historical v1 nevertheless blocked with `live_root_contract_mismatch`, because it compared approved-date as-of rows against a moving latest root contract.

Forward-only review proposal `backend/db/proposals/price_storage_v2_scope_stage_v2.sql` preserves raw↔V2 as-of, receipt, coverage, review, edition and root-identity gates, but treats newer-than-approved latest economics as diagnostic rather than as proof the approved-date reconstruction is wrong. The historical v1 migration remains untouched. Writers require v2 staged evidence; the coordinator stages through v2 and remains unscheduled.

GitHub Actions run `34183532432`, job `101927253176`, succeeded on PostgreSQL 17.6 for validated implementation commit `2efcefa2862001d216d7983d49087fe8166214f0`: **42** unit/integration + **13** source/full-ledger + **6** snapshot replay + **20** writer/security/concurrency + **8** exact-source SQL + **6** coordinator = **95 passing checks**. Pattern Overlay Guardrails also passed.

The new exact-source regression advances the actual modern standard-root latest projection to Sep 7 while leaving Sep 6 historical V2 events/ranges unchanged. It proves the actual root latest reader changes, v1 blocks, Sep 6 raw↔V2 and root identity remain exact, and v2 passes only because the newer latest economics are outside the approved-date acceptance boundary. Identity/as-of differences still block.

No v2 proposal is installed in production. No release gate is enabled. No cron is attached. No public reader is switched. No historical/raw price rows were rewritten or deleted.

Remaining gates: confirm the same latest-date drift with a small live read-only diagnostic; install only new forward migrations with the release gate off; run advisors/ACL checks; perform live dry snapshot/index replay; approve bounded cutover; observe stable cycles; only then retire legacy dependencies and reclaim physical storage.

**Do not merge this PR yet.**
