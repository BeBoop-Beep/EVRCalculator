function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function parseNumberFromLabel(value, fallback = 0) {
  const cleaned = String(value || "").replace(/[^0-9.-]/g, "");
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildRangePoints(totalValue, rawPoints = []) {
  const points = Array.isArray(rawPoints) ? rawPoints : [];
  if (points.length === 0) return [];

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1, max - min);

  return points.map((pointValue, idx) => {
    const daysAgo = points.length - 1 - idx;
    const date = new Date();
    date.setDate(date.getDate() - daysAgo);

    const normalized = (pointValue - min) / span;
    const value = Math.round(totalValue * (0.94 + normalized * 0.12));

    return {
      dateLabel: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      totalValue: value,
    };
  });
}

function buildLabeledSeries(totalValue, labels, multipliers) {
  return labels.map((label, idx) => ({
    dateLabel: label,
    totalValue: Math.round(totalValue * multipliers[idx]),
  }));
}

export function mapPublicOverviewToDashboardData(overview) {
  if (!overview) {
    return {
      commandCenter: {},
      performance: { points: [], periodLabel: "No data" },
      insights: { topMovers: [], allocationSummary: [] },
    };
  }

  const valueStat = overview.snapshotStats?.find((s) => s.id === "snapshot-value");
  const itemsStat = overview.snapshotStats?.find((s) => s.id === "snapshot-items");
  const wishlistStat = overview.snapshotStats?.find((s) => s.id === "snapshot-wishlist");

  const totalValue = parseNumberFromLabel(valueStat?.value, 18245);
  const cardsCount = parseNumberFromLabel(itemsStat?.value, 0);
  const wishlistCount = parseNumberFromLabel(wishlistStat?.value, 0);

  const performancePoints = buildRangePoints(totalValue, overview.performance?.points || []);
  const rangeSeries = {
    "7D": {
      points: performancePoints,
      helper: overview.performance?.trendLabel || "Public trend view over the past week.",
    },
    "1M": {
      points: buildLabeledSeries(totalValue, ["Wk 1", "Wk 2", "Wk 3", "Wk 4", "Now"], [0.92, 0.94, 0.96, 0.99, 1]),
      helper: overview.performance?.trendLabel || "Monthly momentum based on public data.",
    },
    "6M": {
      points: buildLabeledSeries(totalValue, ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"], [0.78, 0.82, 0.86, 0.91, 0.96, 1]),
      helper: "Six-month public trajectory across visible holdings.",
    },
    "1Y": {
      points: buildLabeledSeries(totalValue, ["Q2", "Q3", "Q4", "Q1", "Now"], [0.68, 0.75, 0.84, 0.93, 1]),
      helper: overview.performance?.returnLabel || "One-year public performance trend.",
    },
  };

  const topMovers = (overview.highlights || []).slice(0, 3).map((entry, idx) => ({
    id: `public-mover-${idx + 1}`,
    name: entry.value || "Portfolio Item",
    changePercent7d: safeNumber(6 - idx * 2, 0),
    valueLabel: "Public estimate",
  }));

  return {
    commandCenter: {
      totalValue,
      change24hPercent: 0.91,
      change7dPercent: 4.38,
      cardsCount,
      sealedCount: 0,
      wishlistCount,
      lastSyncedAt: new Date().toISOString(),
      freshnessLabel: "Public",
    },
    performance: {
      periodLabel: overview.performance?.periodLabel || "Last 7 days",
      points: performancePoints,
      rangeSeries,
    },
    insights: {
      topMovers,
      allocationSummary: [
        { id: "public-a1", label: "Cards", valuePercent: 68, valueLabel: "Core holdings" },
        { id: "public-a2", label: "Sealed", valuePercent: 24, valueLabel: "Sealed products" },
        { id: "public-a3", label: "Merchandise", valuePercent: 8, valueLabel: "Other assets" },
      ],
    },
  };
}