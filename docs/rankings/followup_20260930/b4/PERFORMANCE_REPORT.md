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

A production build was served locally and exercised with deterministic Plus
and anonymous route fixtures. The acceptance record is
`evidence/browser-acceptance.json`.

| Measurement | Result |
|---|---:|
| Anonymous catalogue page 1 body | 5,099 bytes |
| Paid Scores page 1 body | 9,184 bytes |
| Paid Economics page 1 body | 14,013 bytes |
| Normal Scores click-to-rows | recorded in JSON |
| Normal Economics click-to-rows | recorded in JSON |
| Injected 250 ms Scores click-to-rows | recorded in JSON |
| Injected 250 ms Economics click-to-rows | recorded in JSON |

The fixture also records every URL, returned ID, and row count. It proves that
normal requests return at most the requested 25-row page, while search, family,
global sort, last-page bounds, and view reset remain server-driven. Timings are
controlled-browser observations, not live database endpoint latency.

`LIVE_LOCAL_PRODUCT_TIMING_BLOCKED`: no authenticated local database/runtime
credentials were supplied, so a fresh live cold/warm endpoint measurement is
not claimed. The authoritative live measurements above remain the live basis.
