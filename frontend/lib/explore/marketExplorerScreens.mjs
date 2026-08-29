export const MARKET_EXPLORER_SCREEN_REGISTRY_VERSION = "market-explorer-screens-v1";

export const MARKET_EXPLORER_SCREENS = Object.freeze([
  { id: "rarity-leaders", label: "Rarity Leaders", description: "Prepared card-rarity markets ranked by 30-day index return.", category: "rotation", asset: "cards", requiredPlan: "plus", type: "rankedPrepared", group: "card", metric: "30D", limit: 10 },
  { id: "sealed-format-leaders", label: "Sealed Format Leaders", description: "Prepared sealed-family markets ranked by 30-day index return.", category: "rotation", asset: "sealed", requiredPlan: "plus", type: "rankedPrepared", group: "sealed", metric: "30D", limit: 10 },
  { id: "momentum-leaders", label: "Momentum Leaders", description: "Prepared markets ranked by transparent trailing 30-day index return.", category: "behavior", asset: null, requiredPlan: "plus", type: "rankedPrepared", group: null, metric: "30D", limit: 10 },
  { id: "largest-drawdowns", label: "Largest Drawdowns", description: "Prepared markets furthest below their own since-tracking index high.", category: "behavior", asset: null, requiredPlan: "plus", type: "rankedDrawdown", group: null, limit: 10 },
  { id: "obtainable-market", label: "Obtainable Market", description: "Cards below $10 on each observation date.", category: "price", asset: "cards", requiredPlan: "plus", type: "builderTemplate", template: { priceSegmentIds: ["obtainable"] } },
  { id: "intermediate-market", label: "Intermediate Market", description: "Cards from $10 to below $100 on each observation date.", category: "price", asset: "cards", requiredPlan: "plus", type: "builderTemplate", template: { priceSegmentIds: ["intermediate"] } },
  { id: "premium-market", label: "Premium Market", description: "Cards at $100 or more on each observation date.", category: "price", asset: "cards", requiredPlan: "plus", type: "builderTemplate", template: { priceSegmentIds: ["premium"] } },
  { id: "new-release-market", label: "New Release Market", description: "Sets 0-180 days from release on each observation date.", category: "release", asset: "cards", requiredPlan: "plus", type: "builderTemplate", template: { releaseAgeCohortIds: ["new"] } },
  { id: "established-market", label: "Established Market", description: "Sets 2-5 years from release on each observation date.", category: "release", asset: "cards", requiredPlan: "plus", type: "builderTemplate", template: { releaseAgeCohortIds: ["established"] } },
  { id: "set-top-ten", label: "Top 10 in Selected Set", description: "Rank the selected set's eligible constituents by price on each date.", category: "chase", asset: "cards", requiredPlan: "premium", type: "builderTemplate", template: { mode: "chase", topN: 10 } },
]);

export function canUseScreen(screen, plan) {
  if (screen?.requiredPlan === "premium") return plan === "premium";
  if (screen?.requiredPlan === "plus") return plan === "plus" || plan === "premium";
  return false;
}

export function validateScreenRegistry(screens = MARKET_EXPLORER_SCREENS) {
  const ids = new Set();
  return screens.every((screen) => {
    if (!screen?.id || !screen.label || !screen.description || !screen.category || !screen.type || ids.has(screen.id)) return false;
    ids.add(screen.id);
    return ["plus", "premium"].includes(screen.requiredPlan) &&
      ["rankedPrepared", "rankedDrawdown", "builderTemplate"].includes(screen.type);
  });
}

const changeValue = (series, key) => Number(series?.changes?.[key]?.percent ?? series?.changes?.[key]?.changePercent);

export function resolveScreenResults(screen, preparedSeries = []) {
  const candidates = (preparedSeries || []).filter((series) => series?.available !== false && !series?.isParent && (!screen.group || series.group === screen.group));
  if (screen.type === "rankedPrepared") {
    return candidates.map((series) => ({ series, value: changeValue(series, screen.metric) }))
      .filter((entry) => Number.isFinite(entry.value)).sort((a, b) => b.value - a.value || String(a.series.key).localeCompare(String(b.series.key))).slice(0, screen.limit);
  }
  if (screen.type === "rankedDrawdown") {
    return candidates.map((series) => {
      const values = (series.trend || []).map((point) => Number(point.value)).filter(Number.isFinite);
      const current = values.at(-1); const high = values.length ? Math.max(...values) : null;
      return { series, value: high > 0 && Number.isFinite(current) ? (current / high - 1) * 100 : null };
    }).filter((entry) => Number.isFinite(entry.value)).sort((a, b) => a.value - b.value || String(a.series.key).localeCompare(String(b.series.key))).slice(0, screen.limit);
  }
  return [];
}

export function draftForScreenResult(screen, result, currentDraft = {}) {
  const clean = { asset: screen.asset || currentDraft.asset || "cards", eraIds: [], setIds: [], segmentIds: [], pokemonIds: [], priceSegmentIds: [], releaseAgeCohortIds: [], mode: "all", topN: null };
  if (screen.type === "builderTemplate") {
    const selectedScope = screen.id === "set-top-ten" ? { eraIds: currentDraft.eraIds || [], setIds: currentDraft.setIds || [] } : {};
    return { ...clean, ...selectedScope, ...screen.template };
  }
  const series = result?.series;
  if (series?.group === "card") return { asset: "cards", segmentIds: [series.backendKey], mode: "all" };
  if (series?.group === "sealed") return { asset: "sealed", segmentIds: [series.backendKey], mode: "all" };
  return clean;
}
