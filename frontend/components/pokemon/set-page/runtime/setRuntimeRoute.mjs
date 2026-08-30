export const SET_RUNTIME_TABS = new Set(["overview", "market", "cards", "pull-rates"]);

export function normalizeSetRuntimeTab(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const aliased = normalized === "rip" || normalized === "analysis" || normalized === "analytics"
    ? "overview"
    : normalized;
  return SET_RUNTIME_TABS.has(aliased) ? aliased : "overview";
}

export function buildSetRuntimeHref(pathname, searchParams, tab, section = null) {
  const params = new URLSearchParams(searchParams?.toString?.() || "");
  const nextTab = normalizeSetRuntimeTab(tab);
  params.set("tab", nextTab);
  if (section) params.set("section", section);
  else params.delete("section");
  if (nextTab !== "cards" || section !== "market-movers") {
    params.delete("card_sort");
    params.delete("movement_filter");
  }
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}

export function resolveSetRuntimeIdentity({ requestedTargetId, selectedTarget, shellPayload }) {
  return String(
    selectedTarget?.id ??
      selectedTarget?.set_id ??
      selectedTarget?.target_id ??
      shellPayload?.set?.id ??
      shellPayload?.setIdentity?.id ??
      shellPayload?.summary?.set_id ??
      requestedTargetId ??
      "",
  ).trim();
}
