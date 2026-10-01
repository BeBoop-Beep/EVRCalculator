# Best-Open presentation contract

## Exact-SKU authority

Product Economics reads the latest Best-Open pointer and rows in one batch. Rows are mapped only by canonical `sealed_product_id`; names and family labels are never join keys. The response includes the exact threshold, exact Best-Open market observation, status, gaps, and independently named evidence dates.

B3 Set Pack Economics reuses the same presentation component with each exact Product object. It does not reintroduce families, aggregate thresholds, or change economics calculations.

## Default cell and details

The default cell contains one threshold price and an accessible info button. Permanent gap/status explanation lines were removed. The popover provides, when available:

- modeled Best-Open threshold;
- current market observation for the same SKU;
- signed dollar and percentage difference;
- explicit directional sentence;
- Best-Open date, market date, status, and independent freshness note;
- MSRP unavailable state.

Difference is `current market - Best-Open threshold`. Positive means market is above threshold; negative means market is below threshold. Percentage is that signed difference divided by current market. A zero/missing market denominator produces no percentage—never `NaN` or infinity.

Missing threshold displays `—` and the popover says unavailable. Missing market evidence omits difference/interpretation. Dates remain separate fields even when they happen to be equal.

## MSRP policy

No authoritative exact-SKU MSRP authority exists in the inspected repository contract. B4 displays no numeric MSRP and never labels current market, retailer price, remembered launch price, or `$0` as MSRP. The popover exposes a concise `MSRP unavailable` state. A future addition must be exact SKU, region, currency, package configuration, source, and source date.

Best-Open remains a model threshold; current market remains an observed price; MSRP remains a manufacturer reference. The component does not conflate them.

## Accessibility

The trigger is a native button with a Product-specific accessible label, `aria-expanded`, and `aria-haspopup=dialog`. Native keyboard activation supports Enter/Space and click/touch. Escape closes and restores trigger focus. Outside pointer interaction, scroll, or resize closes the portal. A visible focus ring is present, and portal positioning is viewport-bounded/mobile-centered.
