# eBay D3 new blind review handoff

Frozen matcher `index_fair_value_ebay_d3_v3` has fingerprint `b5e44641f35c5f846a8d83bc6c777285f6e07707c9c672feef47c55cd67c95ec` and
implementation commit `f744ae4b59e6d9efa02de08a23e07c68ac7c370c`. Benchmark design fingerprint:
`75505bfcbe2e167821a3178b5da192e1240879fe3e4edd75891fa2c55c02d2c6`.

No new certification labels have been viewed. First obtain a fresh capture using the
140-call preregistered budget, exclude all prior item IDs, run frozen v3 before labels
exist, and materialize `PRECISION_BLIND` and `COVERAGE_BLIND` without matcher or price
fields. Human review remains resume-safe and append-only. MEDIUM is diagnostic-only.
