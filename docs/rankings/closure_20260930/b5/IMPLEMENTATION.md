# Bucket 5 implementation

Starting commit: `371dfaa5040a5d46400f3db17c208b580f42f852`.

Branch: `fix/rankings-overview-history-b5-20260930`.

## Result

- Removed selector-selected chips and the capped duplicate legend.
- Added one complete responsive legend with matching markers and accessible per-entity removal.
- Made Overall permanent and supported an authoritative Overall-only chart after final removal.
- Preserved the manual five-Set limit while allowing complete Era presets (within the existing 22-entity request bound).
- Kept colors stable by identity.
- Subdued Overall to 72% opacity while keeping it thicker than entity lines.
- Replaced the crowded tooltip with one date, one Overall, and dynamically sorted signed-delta rows.
- Stopped lines from bridging missing observations.
- Reused already-loaded payloads for local removals and re-adds; no hover request exists.

## Verification

- Focused history/model/contracts: 23/23 passed.
- Focused B1–B4 regression contracts: 32/32 passed.
- Source inspection confirms effect cleanup retains stale-response protection and public access remains gated.
- No backend, publication, metric, calibration, or access-level code changed.

No legitimate `BACKEND_API_BASE_URL` is configured. Status: `FULL_BUILD_BLOCKED_MISSING_BACKEND_API_BASE_URL`. Browser visual acceptance and runtime request timing were not claimed. Process inspection found no competing heavy worker, but missing configuration independently blocks the production/browser path.
