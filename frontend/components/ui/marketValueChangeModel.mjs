const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const MARKET_VALUE_CHANGE_VARIANTS = Object.freeze([
  "hero",
  "chart-summary",
  "table-row",
  "card-tile",
  "ticker",
  "tooltip",
]);

export function toMarketNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMarketValue(value) {
  const parsed = toMarketNumber(value);
  return parsed === null ? "N/A" : currencyFormatter.format(parsed);
}

export function getMarketChangeDirection(changeAmount, changePercent, direction = null) {
  if (direction === "up") return "positive";
  if (direction === "down") return "negative";
  if (["positive", "negative", "neutral"].includes(direction)) return direction;
  const amount = toMarketNumber(changeAmount);
  const percent = toMarketNumber(changePercent);
  const signal = amount ?? percent;
  if (signal === null || Math.abs(signal) < 0.000001) return "neutral";
  return signal > 0 ? "positive" : "negative";
}

export function buildMarketValueChangeModel({
  value,
  changeAmount,
  changePercent,
  windowLabel,
  direction = null,
  unavailable = false,
  accessibleLabel = "Market value",
} = {}) {
  const amount = toMarketNumber(changeAmount);
  const percent = toMarketNumber(changePercent);
  const normalizedWindow = String(windowLabel || "").trim();
  const resolvedDirection = getMarketChangeDirection(amount, percent, direction);
  const valueText = formatMarketValue(value);
  const hasReliableChange = !unavailable && (amount !== null || percent !== null);

  if (!hasReliableChange) {
    const changeText = normalizedWindow ? `${normalizedWindow} change unavailable` : "Change unavailable";
    return {
      valueText,
      changeText,
      direction: "unavailable",
      hasReliableChange: false,
      accessibleText: `${accessibleLabel}: ${valueText}. ${changeText}.`,
    };
  }

  const iconText = resolvedDirection === "positive" ? "\u25b2" : resolvedDirection === "negative" ? "\u25bc" : "\u2014";
  const amountText = amount === null
    ? null
    : Math.abs(amount) < 0.005
    ? currencyFormatter.format(0)
    : `${amount < 0 ? "\u2212" : "+"}${currencyFormatter.format(Math.abs(amount))}`;
  const percentText = percent === null
    ? null
    : Math.abs(percent) < 0.000001
    ? "0.0%"
    : `${percent < 0 ? "\u2212" : "+"}${Math.abs(percent).toFixed(1)}%`;
  const suffix = normalizedWindow ? ` \u00b7 ${normalizedWindow}` : "";
  const visibleChangeText = amountText && percentText
    ? `${amountText} (${percentText})`
    : amountText || percentText;
  const changeText = `${iconText} ${visibleChangeText}${suffix}`;
  const directionText = resolvedDirection === "positive" ? "Positive change" : resolvedDirection === "negative" ? "Negative change" : "No change";
  const accessibleValues = [amountText, percentText].filter(Boolean).join(", ");

  return {
    valueText,
    changeText,
    amountText,
    percentText,
    windowLabel: normalizedWindow,
    direction: resolvedDirection,
    directionText,
    hasReliableChange: true,
    accessibleText: `${accessibleLabel}: ${valueText}. ${directionText}, ${accessibleValues}${normalizedWindow ? ` over ${normalizedWindow}` : ""}.`,
  };
}
