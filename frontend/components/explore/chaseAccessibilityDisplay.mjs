/**
 * Shared Chase Accessibility cell-text formatter.
 *
 * Both Product Rankings (`ProductFamilyRankingsClient.jsx`) and Set Rankings
 * (`ExploreTableClient.jsx`) render the identical backend-authoritative
 * Chase Accessibility block (`{ percent, setRank, setCohortSize }` — see
 * `backend/db/services/chase_accessibility_set_ranking.py`). This module is
 * the ONE place that formats it to text so the two surfaces can never drift
 * apart on rounding, the "%" suffix, or the "Set #X of Y" wording. It
 * performs no ranking arithmetic of its own, only formatting of backend-
 * supplied numbers.
 */

// Locked wording (Overall RIP / Market-Based / Chase Accessibility tooltip
// copy) — never restate scoring weights here.
export const CHASE_ACCESSIBILITY_HELP =
  "How reachable are this set's most important collectible values from a pack? Chase Accessibility is inherited from the product's parent set.";

// Full locked sentence, for contexts (e.g. the Overall RIP explanation
// hierarchy) that state it standalone.
export const MARKET_BASED_HELP_SENTENCE =
  "Market-Based Opening Quality combines Financial RIP with Chase Accessibility.";

// Short form for a column-group tooltip whose visible heading already reads
// "Market-Based Opening Quality" — avoids restating the heading text back to
// the reader inside its own tooltip.
export const MARKET_BASED_HELP = "Combines Financial RIP with Chase Accessibility.";

function number(value) {
  return Number.isFinite(Number(value)) && value !== null && value !== ""
    ? Number(value)
    : null;
}

/**
 * `block` is the projected `chaseAccessibility` shape:
 * `{ value, percent, status, version, chaseDepth, mappedHcMass, setRank, setCohortSize }`.
 * `setLabel` controls whether the rank line reads "Set #X of Y" (the only
 * form ever shown on a product row, per the LOCKED PRINCIPLE that Chase
 * Accessibility never becomes a per-product rank) or, on a table that is
 * already exclusively about sets, the bare "#X of Y" form.
 */
export function chaseAccessibilityDisplay(block, { setLabel = true } = {}) {
  const pct = number(block?.percent);
  if (pct === null) return { primary: "Unavailable", detail: null };
  const primary = `${pct < 0.1 ? pct.toFixed(3) : pct.toFixed(2)}%`;
  const rank = number(block?.setRank);
  const size = number(block?.setCohortSize);
  const detail = rank && size ? `${setLabel ? "Set " : ""}#${rank} of ${size}` : null;
  return { primary, detail };
}
