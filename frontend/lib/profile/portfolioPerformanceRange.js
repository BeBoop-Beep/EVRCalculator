export const PERFORMANCE_TIME_RANGES = ["1D", "7D", "1M", "6M", "1Y", "LT"];

const PERFORMANCE_SERIES = {
  "1D": {
    helper: "One-day movement based on the latest intraday snapshots",
    points: [
      { dateLabel: "Open", totalValue: 18120 },
      { dateLabel: "Mid", totalValue: 18195 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
  "7D": {
    helper: "Best weekly run in 2 months",
    points: [
      { dateLabel: "Mar 24", totalValue: 17120 },
      { dateLabel: "Mar 25", totalValue: 17385 },
      { dateLabel: "Mar 26", totalValue: 17640 },
      { dateLabel: "Mar 27", totalValue: 17530 },
      { dateLabel: "Mar 28", totalValue: 17825 },
      { dateLabel: "Mar 29", totalValue: 18080 },
      { dateLabel: "Mar 30", totalValue: 18170 },
      { dateLabel: "Mar 31", totalValue: 18245 },
    ],
  },
  "1M": {
    helper: "Momentum accelerated through the second half of the month",
    points: [
      { dateLabel: "Wk 1", totalValue: 16740 },
      { dateLabel: "Wk 2", totalValue: 16910 },
      { dateLabel: "Wk 3", totalValue: 17285 },
      { dateLabel: "Wk 4", totalValue: 17860 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
  "6M": {
    helper: "Steady upside driven by sealed strength and premium singles",
    points: [
      { dateLabel: "Oct", totalValue: 14980 },
      { dateLabel: "Nov", totalValue: 15320 },
      { dateLabel: "Dec", totalValue: 15890 },
      { dateLabel: "Jan", totalValue: 16540 },
      { dateLabel: "Feb", totalValue: 17440 },
      { dateLabel: "Mar", totalValue: 18245 },
    ],
  },
  "1Y": {
    helper: "Long-term appreciation remains intact across the full portfolio",
    points: [
      { dateLabel: "Q2", totalValue: 13220 },
      { dateLabel: "Q3", totalValue: 14480 },
      { dateLabel: "Q4", totalValue: 15670 },
      { dateLabel: "Q1", totalValue: 17040 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
  LT: {
    helper: "Performance since portfolio inception",
    points: [
      { dateLabel: "2022", totalValue: 9420 },
      { dateLabel: "2023", totalValue: 11680 },
      { dateLabel: "2024", totalValue: 13970 },
      { dateLabel: "2025", totalValue: 16480 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
};

function resolveLifetimePoints(performanceData) {
  const explicitLifetime = performanceData?.rangeSeries?.LT?.points;
  if (Array.isArray(explicitLifetime) && explicitLifetime.length > 0) {
    return explicitLifetime;
  }

  const candidateSeries = Object.values(performanceData?.rangeSeries || {})
    .map((series) => (Array.isArray(series?.points) ? series.points : []))
    .filter((points) => points.length > 0);

  if (Array.isArray(performanceData?.points) && performanceData.points.length > 0) {
    candidateSeries.push(performanceData.points);
  }

  if (candidateSeries.length === 0) {
    return null;
  }

  return candidateSeries.reduce((longest, current) =>
    current.length > longest.length ? current : longest
  );
}

export function getPerformanceRangeData(selectedRange, performanceData) {
  const range = PERFORMANCE_SERIES[selectedRange] ? selectedRange : "7D";
  const baseSeries = PERFORMANCE_SERIES[range];
  const overrideSeries = performanceData?.rangeSeries?.[range];
  const lifetimePoints = range === "LT" ? resolveLifetimePoints(performanceData) : null;
  const points = overrideSeries?.points?.length
    ? overrideSeries.points
    : lifetimePoints?.length
      ? lifetimePoints
      : range === "7D" && performanceData?.points?.length
        ? performanceData.points
        : baseSeries.points;

  const currentValue = points[points.length - 1]?.totalValue || 0;
  const startValue = points[0]?.totalValue || 0;
  const changeDollar = currentValue - startValue;
  const changePercent = startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0;

  return {
    range,
    helper: overrideSeries?.helper || (range === "LT" && lifetimePoints?.length ? "Performance since portfolio inception" : baseSeries.helper),
    points,
    currentValue,
    changeDollar,
    changePercent,
  };
}

export function getPerformanceRangeMetrics(points = []) {
  const values = points
    .map((point) => Number(point?.totalValue))
    .filter((value) => Number.isFinite(value));

  if (values.length === 0) {
    return {
      currentValue: 0,
      periodChange: 0,
      periodRoi: null,
      periodHigh: 0,
      periodLow: 0,
    };
  }

  const startValue = values[0];
  const endValue = values[values.length - 1];

  return {
    currentValue: endValue,
    periodChange: endValue - startValue,
    periodRoi: startValue > 0 ? ((endValue - startValue) / startValue) * 100 : null,
    periodHigh: Math.max(...values),
    periodLow: Math.min(...values),
  };
}

function pickFirstFiniteNumber(...candidates) {
  for (const candidate of candidates) {
    const numeric = Number(candidate);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }

  return null;
}

function getSeriesBasisValues(series) {
  return {
    investedValue: pickFirstFiniteNumber(
      series?.investedValue,
      series?.totalInvested,
      series?.invested,
      series?.costBasis,
      series?.basisValue,
      series?.basis
    ),
    totalProfit: pickFirstFiniteNumber(
      series?.totalProfit,
      series?.profitValue,
      series?.profit,
      series?.gain,
      series?.changeDollar
    ),
    roiPercent: pickFirstFiniteNumber(
      series?.roiPercent,
      series?.periodRoi,
      series?.changePercent,
      series?.roi
    ),
  };
}

/**
 * Build owner-only metric cards using selected range basis when available.
 * For LT, this resolves to lifetime basis.
 */
export function getPrivatePerformanceMetrics({
  selectedRange,
  performanceData,
  rangeMetrics,
  currentValue,
  fallbackInvestedValue,
}) {
  const range = PERFORMANCE_SERIES[selectedRange] ? selectedRange : "7D";
  const selectedSeries = performanceData?.rangeSeries?.[range];
  const lifetimeSeries = performanceData?.rangeSeries?.LT;

  const selectedBasis = getSeriesBasisValues(selectedSeries);
  const lifetimeBasis = getSeriesBasisValues(lifetimeSeries);

  const selectedInvestedFallback = Number.isFinite(rangeMetrics?.currentValue - rangeMetrics?.periodChange)
    ? rangeMetrics.currentValue - rangeMetrics.periodChange
    : null;

  const lifetimeCurrentValue = Number.isFinite(currentValue)
    ? currentValue
    : Number.isFinite(rangeMetrics?.currentValue)
      ? rangeMetrics.currentValue
      : 0;

  const lifetimeInvested = pickFirstFiniteNumber(
    lifetimeBasis.investedValue,
    fallbackInvestedValue,
    selectedBasis.investedValue,
    selectedInvestedFallback
  ) || 0;

  const lifetimeProfit = pickFirstFiniteNumber(
    lifetimeBasis.totalProfit,
    lifetimeCurrentValue - lifetimeInvested
  ) || 0;

  const lifetimeRoi = pickFirstFiniteNumber(
    lifetimeBasis.roiPercent,
    lifetimeInvested > 0 ? (lifetimeProfit / lifetimeInvested) * 100 : null
  );

  const selectedInvested = range === "LT"
    ? lifetimeInvested
    : pickFirstFiniteNumber(selectedBasis.investedValue, selectedInvestedFallback, lifetimeInvested) || 0;

  const selectedProfit = range === "LT"
    ? lifetimeProfit
    : pickFirstFiniteNumber(
      selectedBasis.totalProfit,
      Number.isFinite(rangeMetrics?.periodChange) ? rangeMetrics.periodChange : lifetimeCurrentValue - selectedInvested
    ) || 0;

  return {
    lifetimeRoi,
    totalInvested: selectedInvested,
    totalProfit: selectedProfit,
  };
}