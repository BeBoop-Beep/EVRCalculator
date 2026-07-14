function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatPerformanceRatio(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "\u2014";
  }
  return `${parsed.toFixed(2)}x`;
}

export function formatReturnMultiple(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "\u2014";
  }
  return `${Math.abs(parsed).toFixed(2)}x`;
}

export function formatPerformanceCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "\u2014";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parsed);
}

export function formatRatioWithCurrency(ratioValue, dollarValue) {
  const ratioText = formatReturnMultiple(ratioValue);
  const parsedDollarValue = toNumber(dollarValue);
  if (parsedDollarValue === null) {
    return ratioText;
  }
  return `${ratioText} (${formatPerformanceCurrency(Math.abs(parsedDollarValue))})`;
}

// Single source of truth for the three plotted series' labels. The default
// "market" variant powers Overview's quick-read chart; the "simulation"
// variant keeps the Simulation Results (Opening P vs C) chart technical, naming
// the raw percentile-vs-cost ratios instead of the simplified reader copy.
export const PERFORMANCE_SERIES_LABELS = {
  market: {
    mean: "Expected Value",
    median: "Typical Return",
    p95: "Realistic Upside",
  },
  simulation: {
    mean: "Expected Value vs Cost",
    median: "50th Percentile vs Cost",
    p95: "95th Percentile vs Cost",
  },
};

export function getPerformanceSeriesLabels(variant = "market") {
  return PERFORMANCE_SERIES_LABELS[variant] || PERFORMANCE_SERIES_LABELS.market;
}

export function buildPerformanceTooltipRows(row = {}, packCost = null, variant = "market") {
  const effectivePackCost = toNumber(row?.packCost) ?? toNumber(packCost);
  const labels = getPerformanceSeriesLabels(variant);
  const rows = [];

  if (toNumber(row?.p95CostRatio) !== null || toNumber(row?.p95Value) !== null) {
    rows.push({
      key: "p95",
      label: labels.p95,
      value: formatRatioWithCurrency(row?.p95CostRatio, row?.p95Value),
    });
  }

  rows.push(
    {
      key: "average",
      label: labels.mean,
      value: formatRatioWithCurrency(row?.meanCostRatio, row?.meanValue),
    },
    {
      key: "typical",
      label: labels.median,
      value: formatRatioWithCurrency(row?.medianCostRatio, row?.medianValue),
    },
    {
      key: "break-even",
      label: "Break-even",
      value: "1.00x",
    },
    {
      key: "pack-cost",
      label: "Pack Market Price",
      value: formatPerformanceCurrency(effectivePackCost),
    }
  );

  return rows;
}
