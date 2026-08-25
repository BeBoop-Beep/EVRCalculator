const RECENT_WINDOWS = new Set(["1D", "7D", "30D"]);

export function selectSetMarketMiniTrend(target, windowKey) {
  const movement = target?.windows?.[windowKey];
  if (!movement?.startDate || !movement?.endDate) return [];
  const source = RECENT_WINDOWS.has(windowKey) ? target?.recentDailyTrend : target?.trend;
  return (Array.isArray(source) ? source : [])
    .map((point) => Array.isArray(point) ? { date: String(point[0] || "").slice(0, 10), value: Number(point[1]) } : null)
    .filter((point) => point && point.date >= movement.startDate && point.date <= movement.endDate && Number.isFinite(point.value))
    .sort((left, right) => left.date.localeCompare(right.date));
}
