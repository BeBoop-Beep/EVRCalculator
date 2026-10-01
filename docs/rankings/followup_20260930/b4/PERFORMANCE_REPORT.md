# Product Rankings performance report

## Authoritative live evidence supplied for B4

- Paid Full Market cohort: 138 Products.
- Public catalogue: approximately 1,774 identities.
- Old persisted Product JSON subtree: approximately 524 KB.
- Direct old JSON subtree extraction: approximately 52 ms before transfer and deserialization.
- Relational 25-row Scores sample: approximately 6.6 ms.
- Exact economics read: approximately 115 ms cold and 1.36 ms immediate warm.

## Implementation inference

Paid Scores no longer reads or transfers the large Product snapshot subtree.
The shared 138-row publication authority is cached by snapshot ID, publication
timestamp, and cohort fingerprint; entitlement remains request-local. Public
and paid browser cache keys are separate and include query parameters.

Normal Economics requests first select the 25-row page and then issue one
batched exact-simulation read and one page-bounded Best-Open read. Exact-field
sorts require a bounded cohort simulation batch so ordering remains global.

## Local fixture/build evidence

No live database or authenticated browser timing was performed in this
worktree. Therefore cold/warm endpoint time, browser click-to-rows, request
count, and response-byte deltas remain deployment-environment measurements;
the supplied live evidence above is not presented as local fixture timing.
