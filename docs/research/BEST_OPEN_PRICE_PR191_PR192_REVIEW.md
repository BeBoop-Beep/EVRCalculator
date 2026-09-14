# Best-Open Price: review of PRs 191 and 192

Reviewed baseline: `e7a2d4658207fe924e8c33e8938016ef3cbba385`.
Review date: 2026-09-14.

## Outcome

The original completion statement was too confident. The original 72-test suite
passed again, but eleven new adversarial tests failed before corrections. This
review covers the Rankings and Product Detail projections, independent capability
filtering, current-source runner, scheduler chain, checkpoints/cache behavior,
exact-search assumptions and the publication RPC. It is not a claim that the
entire application or every production opening has been validated.

## Confirmed findings and corrections

### High: threshold maximality was local, not necessarily global

The inherited search engine could stop after the first losing leader bracket,
and a five-sentinel test could miss a winning region within a quantity interval.
`P* wins / P*+1 cent loses` does not by itself prove there is no higher winning
price. Synthetic examples reproduced both failures. The previous 100-case oracle
only generated monotone winning sets, so it could not catch them.

The correction scans reachable quantity intervals in descending-price order and
uses exact descending cents within each interval. It retains the canonical
prepared Financial/V12 scorer and bitwise-compatible quantity construction.
Candidate-score caching is bounded at 2,048 entries; product quantity caching is
still bounded. A new deterministic 1,000-case oracle includes arbitrary
non-monotone winning sets. No claim is made that the existing 138 production
prices are wrong: this is a demonstrated general correctness defect, not a
completed remeasurement of that particular cohort.

### High: concurrent publication was not serialized

The live RPC used an unlocked source SELECT. A sequential T1-to-T2 rejection test
was not a concurrent transaction test. The additive migration locks the source
snapshot, then its latest pointer (matching upstream writer lock order), and the
Full Market source rows during the short publication transaction. No transaction
is held during the expensive Python build. A unique source-publication/method
index prevents duplicate authorities. Real two-connection tests exercise source
replacement and simultaneous identical publication.

The same migration also requires canonical V12/model identity, the correct
leader/#2 benchmark, complete cohort membership, positive finite cent prices,
exact quantity allocation and reconciled price gaps. Idempotent retries compare
normalized persisted JSONB content, so row order is not a false conflict.

### High: scheduled rebuild could be skipped after a successful base ranking

PR 192 attached Best-Open to the Windows BAT only when the entire preceding job
exited zero. The preceding job can publish Budget Rankings while an unrelated
Market audit fails. The hook now lives immediately after Budget Ranking in the
shared shell chain and handles both PUBLISHED and NO_NEW_AUTHORITY, independently
of unrelated audit results. Both manual and scheduled invocations use it; all
real failure exit codes remain failures. Slack delivery is best-effort.

### High: current-source scoring and evidence could use different Collector values

The runner read Collector Appeal from mutable simulation results but copied
persisted source evidence into the publish payload. It now scores with the exact
published source Collector input, verifies each original physical strategy before
counterfactual search, and fingerprints all Full Market source values, not only
Chase tuples. The wrapper passes the same database client into the runner.

### Medium: incomplete engine evidence could pass publication validation

The validator accepted a missing next-cent verdict, a wrong adjacent cent, a wrong
quantity, fractional-cent prices, a wrong engine method and missing current
quantity. It now validates numeric finiteness, cents, allocation, direction,
status, source/benchmark identity and values, explicit neighboring outcomes and
full source identity. Serialization failures return structured failures. Final
read-back checks actual published row values, not only count/UUID.

### Medium: retry/checkpoint and UI cache reliability

Checkpoints are atomically replaced and tied to source content, model identity,
NumPy runtime, execution revision, product set and batch configuration. Invalid
or incompatible files are quarantined; complete same-source results can be
reused after a failed publish instead of recomputing the cohort. Shared reports
are no longer used as proof of the current shell invocation's success.

Product session-cache entries expire after 60 seconds. A forced refresh and
cache-clear cannot be overwritten by an older pending response. Rapid budget
switches guard both success and failure callbacks by the active request, and
abandoning a subscriber no longer aborts a shared cached fetch. A missing
Best-Open layer has an explicit refresh action; an invalid Best-Open sort falls
back to ordinary ranking.

### Medium: presentation and capability contracts

“Or lower” and continuous “up to” wording implied every cheaper purchase price
was proven to win, which quantity discontinuities do not establish. Copy now
claims the tested threshold price only, and Product Detail explicitly states the
whole-unit quantity and fixed comparison budget. Missing publication is not
called an actively running refresh without evidence of a running worker.

Product Detail now checks FEATURE_BEST_OPEN_PRICE independently rather than
implicitly coupling it to Product RIP. Basic was already stripped server-side;
this closes the separate-capability contract and avoids future packaging drift.

### Medium: public ranking reads could combine different publications

The public reader captured one snapshot, but its nested Full Market loader
resolved latest again (and again inside the budget loader). A concurrent
publication could attach newer rows to the earlier display/source metadata.
The reader now passes one captured snapshot through every layer and rechecks
that exact header after reading rows. A changed same-ID publication is refused;
it is never silently substituted by a new latest snapshot. Four behavioral
regressions cover capture reuse and mid-read replacement.

## Validation at the local review checkpoint

- Original focused baseline: 72 passed.
- New pre-fix adversarial regressions: 11 failed (confirmed reproductions).
- Expanded local Python matrix: 540 passed, 5 conditional skips.
- Frontend model/cache/access/presentation tests: 73 passed.
- Global synthetic exact-search oracle: 1,000 non-monotone cases passed.
- Native process lock kill/recovery: passed on Linux; Windows CI is a separate gate.
- Real PostgreSQL 17 integration/concurrency suite: 50 passed against a fresh
  isolated PostgreSQL 17.11 service, including genuine two-connection races,
  value rejection, rollback, idempotency and SET ROLE permission checks.
- Initial CI replay: 508 Python tests passed, 5 conditional skips; 73 frontend
  tests passed. Final PR checks and native Windows are reported separately.

The corrective migration is separate from the already-applied original migration;
the original mirrored SQL has not been edited. CI uses an isolated loopback-only
`best_open_test` database, fixture data and test credentials, never production.

## Limits that must not be hidden

The revised global search has not yet completed a new 138-product production-data
replay. The earlier 64.6-minute measurement belongs to the old search path and is
not a measured runtime for this correction. Scoring and distribution formulas
are unchanged, but newly explored winning regions can legitimately change a
previous locally maximal answer. A full new-current-source read-only canary is
required before claiming complete cohort output/performance acceptance.

CI does not establish authenticated visual QA, the local D:\EVRCalculator
checkout state, or that an actual Windows Task Scheduler run has executed the
new code. This review does not release to main or modify production threshold
rows. Production RPC/schema application and live verification must be reported
separately from the source-code corrections.
