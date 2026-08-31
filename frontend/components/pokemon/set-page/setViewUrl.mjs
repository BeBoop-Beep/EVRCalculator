const SET_TABS = new Set(["overview", "market", "cards", "pull-rates"]);

export function normalizeSetViewTab(value) {
  const raw = String(value || "").trim().toLowerCase();
  const normalized = { rip: "overview", analysis: "overview", analytics: "overview" }[raw] || raw;
  return SET_TABS.has(normalized) ? normalized : "overview";
}

export function buildSameSetViewUrl({ pathname, searchParams, tab, section = null, extra = {} }) {
  const params = new URLSearchParams(searchParams?.toString?.() || String(searchParams || ""));
  params.set("tab", normalizeSetViewTab(tab));
  if (section) params.set("section", section);
  else params.delete("section");
  Object.entries(extra).forEach(([key, value]) => {
    if (value === null) params.delete(key);
    else params.set(key, value);
  });
  return `${pathname}?${params.toString()}`;
}
