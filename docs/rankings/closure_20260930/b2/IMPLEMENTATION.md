# Bucket 2 implementation

Base: `b9909b146795f1d274310fcdc8dfd3d4ac2d14f4`  
Branch: `fix/rankings-shared-presentation-b2-20260930`  
Worktree: `D:\EVRCalculator-rankings-b2`

## Implemented

- Era/Set benchmark scores retain their source value, purple outlined badge, `/10`, rank semantics, and screen-reader label. The redundant visible caption and benchmark-position arrow are removed.
- Financial, Collector, and Chase components render as neutral tabular numbers. Desktop headings supply visible context; mobile retains an accessible metric name.
- Era component cells use the same neutral primitive as Set component rows.
- Set Overall continues through `SetIdentity`. Paid Set scorecards, detailed Pack Economics, and Overview Top Set now receive logo/symbol fields through one bounded server-side Set projection. Pack parents use `SetIdentity` on desktop and mobile. Existing fallback remains logo -> symbol -> initials.
- Rankings-specific primary, secondary, Product family, Product Scores/Economics, and Card Collector controls use neutral white selected styling with a visible violet focus ring. The default shared segmented-control styling is unchanged unless a Rankings variant is requested.
- B1 endpoint gates and public projections are unchanged.

Product and Card primary artwork were not replaced. Their secondary Set columns do not currently receive a common artwork identity contract; introducing additional Product/Card response fields was not necessary to complete the bounded primary Set surfaces and is left for the later identity/API bucket.

## Product safety

`B4_PENDING_PRODUCT_SCORE_REFERENCE`

Product `overallRipScore` remains the existing absolute 0–100 V12 value. Bucket 2 adds no division by ten, clamp, fabricated 5.0 reference, score-model write, or publication change. Product benchmark publication/calibration remains out of scope.

## Data-access shape

- Paid Set scorecards: existing single batched `sets.in_(id, ids)` projection adds two small URL fields.
- Detailed Pack Economics: one `sets.in_(id, opening_set_ids)` artwork projection for all parent rows.
- Overview: one bounded Top Set identity lookup.
- No client-side metadata fetch and no request per rendered row.

No migration, publication, production data, membership, scoring model, or deployment behavior was changed.
