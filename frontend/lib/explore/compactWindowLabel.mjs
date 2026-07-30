// Display-only abbreviation for timeframe chips below 1200px. This changes the
// visible glyph and nothing else: the window key, its definition, the data it
// selects and the desktop wording are all untouched.
//
// Only labels that are genuinely too long for a compact chip are abbreviated.
// 1D / 7D / 30D / 3M / 6M / 1Y are already compact and pass through unchanged.
const COMPACT_WINDOW_LABELS = new Map([
  ["lifetime", "LT"],
]);

export function getCompactWindowLabel(key, label) {
  const normalizedKey = String(key ?? "").trim().toLowerCase();
  const compact = COMPACT_WINDOW_LABELS.get(normalizedKey);
  if (compact) {
    return compact;
  }
  // Fall back to matching on the label itself, so a window defined elsewhere
  // with the same wording still abbreviates.
  const normalizedLabel = String(label ?? "").trim().toLowerCase();
  return COMPACT_WINDOW_LABELS.get(normalizedLabel) || String(label ?? "");
}

// True when the compact glyph differs from the full wording, which is the only
// case that needs an explicit accessible name.
export function needsAccessibleWindowLabel(key, label) {
  return getCompactWindowLabel(key, label) !== String(label ?? "");
}
