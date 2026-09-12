# eBay Pricing Integration Handoff

No eBay signal is approved for canonical pricing yet.

After identity acceptance, `EXACT_HIGH_CONFIDENCE` raw listings with explicit or seller-stated NM condition may support a separate **asking-price distribution**: median, trimmed mean, quartiles, IQR, minimum after outlier review, seller count, and fixed/auction composition. `Ungraded` without NM evidence may contribute to broad active-listing counts but not an NM asking-price estimate.

Active asks are not completed sales. They may be stale, repeatedly relisted, overpriced, multi-quantity, or never transact. Browse listing count means listing records—not copies—and seller count means distinct exposed seller identifiers. Quantity depth is unavailable. The estimated `total` field is diagnostic only.

Required safeguards are append-only observed/captured timestamps, separate active-supply and asking-price authorities, explicit condition states, high-confidence identity only, price-outlier diagnostics after identity, staleness tracking across snapshots, source-confidence metadata, and no silent fallback from ambiguous matches.

Completed-sale observations, if later sanctioned, must remain a separate realized-price authority. D2 does not change TCGplayer or any canonical card price.
