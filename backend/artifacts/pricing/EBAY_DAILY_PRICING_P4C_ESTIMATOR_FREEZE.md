# P4C: eBay active-ask source estimator V1

Frozen version: `ebay_active_ask_lower3_seller_median_v1`. Repository search found no prior use of that literal. Source is `eBayActiveAsk`; evidence means active fixed-price asks, not sales. Market date: 2026-09-19. The [replay artifact](ebay_p4c_97cff77b2a1c4b3e9c5d9cfc862d1c8c.json) has SHA-256 content fingerprint `c1f8d1675c7143193e0c0112450215e3a9523a2cbf46aade2fca1e813219c737`.

The frozen computation uses P4A's exact physical identity, English positive and veto policy, NM-compatible condition, executable fixed-price option, and known USD landed ask. It excludes unresolved language. It deduplicates item IDs, keeps the cheapest eligible item per identified seller, sorts those seller-distinct asks, requires at least five sellers, and takes the median of the three cheapest asks. A missing seller identity is excluded. One ask alone is fragile; an all-listing median can let prolific or aspirational sellers dominate. Five total sellers provide surrounding depth for the three competitive asks. The P4B leave-one-seller-out shifts on the eight five-seller cards were at most 22%, so the observed evidence does not contradict this freeze. TCGplayer prices were never optimization labels.

`SUFFICIENT` means at least five sellers; `THIN` means three or four; `INSUFFICIENT` means fewer than three. Only `SUFFICIENT` with a resolved variant produces a numeric persisted price. Replay produced 8 sufficient, 2 thin, and 20 insufficient cards; two sufficient cards lack resolved variants. Six source rows were inserted into `public.ebay_active_ask_price_estimates_v1`. The table is isolated from observations, events, current, canonical, and latest price views. Its unique day/variant/version key and insert-only service grant make changed evidence fail on ordinary replay; the source artifact records listing IDs, seller hashes, landed asks, policy version, and fingerprints. The P4 capture was local rather than a P3 evidence-table run, so `evidence_row_id` is null in provenance; listing IDs and the immutable local capture files provide the replay link.

| Canonical card ID prefix | Variant prefix | Listings/sellers | Lowest three USD | Estimate | TCGplayer | Difference |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| e4b73b72 | 33aae8ca | 5/5 | 4.00, 4.75, 4.98 | 4.75 | 3.63 | +30.9% |
| f13e4255 | 63191dd8 | 5/5 | 1.20, 2.35, 2.43 | 2.35 | 0.25 | +840.0% |
| b38102f7 | 9543c2f9 | 5/5 | 14.99, 16.00, 16.96 | 16.00 | 18.45 | -13.3% |
| 7781f22e | 5c4c7dc2 | 5/5 | 2.90, 2.99, 3.28 | 2.99 | 2.03 | +47.3% |
| 3695a310 | b6e430da | 5/5 | 0.99, 0.99, 0.99 | 0.99 | 0.17 | +482.4% |
| 02768af4 | 3dd0f4fa | 5/5 | 50.98, 55.94, 59.00 | 55.94 | 51.17 | +9.3% |

TCGplayer comparisons are diagnostics only. No high-value card reached five sellers, and the low-price shipping floor contributes to large ratios. Thin cards receive no fallback price. The new table migration is byte-identical in both migration trees and was applied; no generic pricing write occurred. Focused preexisting estimator and English-policy tests: 7 passed.
