function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getStableSetId(target) {
  return String(target?.set_id ?? target?.id ?? target?.target_id ?? "").trim() || null;
}

export function buildPreviousSetValueRanks(targets) {
  return (Array.isArray(targets) ? targets : [])
    .map((target) => ({
      id: getStableSetId(target),
      value: toFiniteNumber(target?.previousChecklistSetValue7d ?? target?.previous_checklist_set_value_7d),
    }))
    .filter(({ id, value }) => id && value !== null && value > 0)
    .sort((left, right) => right.value - left.value || left.id.localeCompare(right.id))
    .reduce((lookup, row, index) => lookup.set(row.id, index + 1), new Map());
}

export function formatRankMovement(previousRank, currentRank, status = "available", interval = "1d") {
  const daily = interval === "1d";
  if (status === "new") return { text: "NEW", label: daily ? "New to the current ranking" : "No comparable set value seven days ago" };
  if (status !== "available") return { text: "N/A", label: daily ? "Previous-day ranking unavailable" : "Seven-day ranking history unavailable" };
  const previous = toFiniteNumber(previousRank);
  const current = toFiniteNumber(currentRank);
  if (previous === null || current === null) return { text: "N/A", label: daily ? "Previous-day ranking unavailable" : "Seven-day ranking history unavailable" };
  const movement = previous - current;
  if (movement > 0) return { text: `↑${movement}`, label: daily ? `Up ${movement} positions since yesterday` : `Up ${movement} positions over seven days` };
  if (movement < 0) return { text: `↓${Math.abs(movement)}`, label: daily ? `Down ${Math.abs(movement)} positions since yesterday` : `Down ${Math.abs(movement)} positions over seven days` };
  return { text: "—", label: daily ? "No rank change since yesterday" : "No rank change over seven days" };
}

export function getSetValueMovement(target) {
  const current = toFiniteNumber(target?.checklistSetValue ?? target?.checklist_set_value);
  const previous = toFiniteNumber(target?.previousChecklistSetValue7d ?? target?.previous_checklist_set_value_7d);
  const status = target?.setValueComparisonStatus7d ?? target?.set_value_comparison_status_7d;
  if (status !== "available" || current === null || previous === null || previous <= 0) return null;
  const amount = current - previous;
  return { amount, percent: (amount / previous) * 100 };
}
