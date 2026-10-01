# Financial RIP history graph contract

## Permanent Overall series

Overall Financial RIP is the permanent comparison line. It is never a removable selection and never receives a remove control. Once a bounded history response has been loaded, removing the final Set/Era rebuilds the chart with no entity series while retaining the authoritative same-date Overall values embedded in those response rows. No dummy entity, all-history query, local average, or fabricated reference is used.

Overall remains thicker than entity lines (`3` versus `1.75`) with `0.72` stroke opacity, making it a strong but slightly subdued reference.

## Selector and legend responsibilities

The searchable selector chooses entities and renders no selected-name chip list (`showChips=false`). One visible legend communicates plotted lines. Overall appears first without a remove button. Every user series has its stable color marker, name, and accessible remove button. Mobile uses horizontal scrolling; desktop wraps. No series is hidden after five.

Manual Set changes retain the five-Set product limit. An Era preset uses all its Sets and bypasses only that manual cap. The existing client/API hard bound remains 22 Sets/Eras per request; it is not bypassed. Removing an Era member removes only that identity and does not rebuild or truncate the remainder.

## Stable colors

Entity colors use `stableEntityColor(entity_id)`, a deterministic identity hash into the existing palette. Array position is irrelevant. Line, legend marker, and tooltip marker all use the series object's same color. Removing and re-adding an identity restores its color.

## Tooltip

The tooltip shows the hovered date once, same-date Overall once, then valid selected entities. Entity rows are sorted by hovered score descending, then case-insensitive name and stable ID. Each row contains the matching color marker, name, and signed score-point delta.

Delta is `entity absolute Financial RIP - same-date Overall Financial RIP`. Positive uses `+x.xx ↑`; negative uses `−x.xx ↓`; equality uses `±0.00`. This is score points, not percent change. If Overall is missing, delta is unavailable. Entity observations missing at the timestamp are omitted and never converted to zero.

Rank, cohort, repeated dates, and repeated “Financial RIP” labels are absent from the visible tooltip.

## History integrity and requests

Observed dates remain authoritative. Lines use `connectNulls={false}`; no forward fill, backfill, interpolation, zero substitution, or gap bridging is introduced. Date-window computation and searchable Set/Era controls are unchanged.

Removing a currently loaded series—including the final series—is local and makes zero history requests. Re-adding a series already present in the loaded payload is also local. Adding an unloaded series, changing mode/preset to new identities, changing time window, or retrying performs one bounded request. Tooltip hover performs no request. Existing effect cleanup rejects stale late responses.

Financial history remains Index Plus protected. B1 public headlines do not change this boundary.
