# Price Storage V2 integration — draft, no production cutover

## Current milestone

A live Sep 6 production read-only canary proved raw↔V2 as-of price parity, complete source/shadow receipts, zero missing prices, zero review-required cards, and correct combined-root candidates for Evolving Skies, Crown Zenith + Galarian Gallery, and Celebrations + Classic Collection. Historical v1 still blocked because it compared those approved-date rows to a moving latest root contract.

Forward-only `canonical_asof_scope_split_v2` is now implemented only in review proposals. It preserves approved-date/raw↔V2/receipt/coverage/review/edition/root-identity gates while treating newer-than-approved latest economics as diagnostic rather than a false approved-date mismatch. Historical v1 SQL remains untouched.

GitHub Actions run `34183532432`, job `101927253176`, passed PostgreSQL 17.6 with **95 checks**: 42 unit/integration, 13 migration/source/full-ledger, 6 snapshot replay, 20 writer/security/concurrency, 8 exact-source SQL, and 6 coordinator. The new exact-source regression reproduces the real date-drift condition by advancing the actual standard-root latest projection to Sep 7 while preserving Sep 6 historical V2 state; v1 blocks and v2 passes only after exact as-of and root-identity parity.

No v2 proposal is installed in production. No release gate is enabled. No cron is attached. No public reader is switched. No historical/raw rows were rewritten or deleted.

Remaining gates: small live read-only latest-date confirmation; install only new forward migrations with gate off; advisors/ACL checks; live dry snapshot/index replay; bounded producer cutover; stable-cycle observation; then dependency retirement and physical storage reclamation.

**Do not merge this PR yet.**
