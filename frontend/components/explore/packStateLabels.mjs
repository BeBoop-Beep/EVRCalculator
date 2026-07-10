// Pure, framework-free helpers for the Simulation Results → Pack Paths tab.
// Normal-state names arrive in inconsistent shapes — both compact camelCase
// (`DoubleRareOnly`, `IrPlusRare`) and already-spaced (`Double Rare Only`,
// `Ir Plus Rare`) — and both should collapse to a single readable label so the
// list stays short and doesn't need an internal scrollbar.

const PACK_STATE_ACRONYMS = {
  ir: "IR",
  sir: "SIR",
  sar: "SAR",
  sr: "SR",
  ar: "AR",
};

function splitPackStateWords(raw) {
  return String(raw || "")
    // split camelCase / PascalCase boundaries: fooBar -> foo Bar
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    // split acronym-then-word boundaries: IRPlus -> IR Plus
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    // snake_case / kebab-case / stray separators
    .replace(/[_\-]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

// Canonical display label for a normal-state name. Acronyms stay uppercase and
// the connector word "Plus" becomes "+" so e.g. `IrPlusRare` and
// `Ir Plus Rare` both render as "IR + Rare".
export function normalizePackStateLabel(raw) {
  const words = splitPackStateWords(raw);
  if (words.length === 0) {
    return "";
  }
  const rendered = words.map((word) => {
    const lower = word.toLowerCase();
    if (lower === "plus" || word === "+") {
      return "+";
    }
    if (PACK_STATE_ACRONYMS[lower]) {
      return PACK_STATE_ACRONYMS[lower];
    }
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  });
  return rendered.join(" ").replace(/\s*\+\s*/g, " + ").trim();
}

// Collapse normal-state rows by their normalized display label (summing counts
// of duplicates), sort by count desc, and optionally keep only the top N. Rows
// may be [name, count] tuples or { name/label, count } objects.
export function aggregateNormalStateRows(rows, { topN = null } = {}) {
  const byLabel = new Map();

  for (const entry of Array.isArray(rows) ? rows : []) {
    const rawName = Array.isArray(entry) ? entry[0] : entry?.name ?? entry?.label;
    const rawCount = Array.isArray(entry) ? entry[1] : entry?.count;
    const count = Number(rawCount);
    if (!Number.isFinite(count)) {
      continue;
    }
    const label = normalizePackStateLabel(rawName);
    if (!label) {
      continue;
    }
    byLabel.set(label, (byLabel.get(label) || 0) + count);
  }

  const merged = Array.from(byLabel.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count);

  if (topN === null || topN === undefined || merged.length <= topN) {
    return { rows: merged, hiddenCount: 0 };
  }
  return { rows: merged.slice(0, topN), hiddenCount: merged.length - topN };
}
