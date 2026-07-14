# Changelog

## Unreleased

- Coordinate Pokemon Cards and Market Dashboard snapshot generation with a
  shared canonical selected-price context, generation UUID, strict movement
  parity gate, Top Chase 1D/7D/30D contracts, and cross-generation runtime
  diagnostics.
- Keep Top Chase short-window charts constrained to history-derived 1D, 7D,
  and 30D ranges while preferring usable persisted deltas and explicitly
  falling back when legacy or malformed movement metadata is encountered.
- Serve the persisted complete Market Movers `all` ranking from the slim
  endpoint so the Overview 7D banner matches the first ten eligible Cards 7D
  Movers without directional-array truncation or client-side re-ranking.
