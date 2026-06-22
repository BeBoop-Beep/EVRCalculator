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

export function buildPerformanceTooltipRows(row = {}, packCost = null) {
  const effectivePackCost = toNumber(row?.packCost) ?? toNumber(packCost);
  const rows = [];

  if (toNumber(row?.p95CostRatio) !== null || toNumber(row?.p95Value) !== null) {
    rows.push({
      key: "p95",
      label: "Big Hit Upside",
      value: formatRatioWithCurrency(row?.p95CostRatio, row?.p95Value),
    });
  }

  rows.push(
    {
      key: "average",
      label: "Expected Value",
      value: formatRatioWithCurrency(row?.meanCostRatio, row?.meanValue),
    },
    {
      key: "typical",
      label: "Typical Return",
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
