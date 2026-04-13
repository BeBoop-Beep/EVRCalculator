import PropTypes from "prop-types";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatPercent(percent) {
  if (typeof percent !== "number" || Number.isNaN(percent)) {
    return "—";
  }

  const absolute = Math.abs(percent).toFixed(2);
  const sign = percent > 0 ? "+" : percent < 0 ? "-" : "";
  return `${sign}${absolute}%`;
}

function formatSignedCurrency(value) {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${currencyFormatter.format(Math.abs(value))}`;
}

/**
 * Portfolio Metrics Row Component
 * 
 * Displays key performance metrics in a responsive horizontal layout:
 * - Current Value (optional)
 * - Period Change (with signed currency)
 * - Period Return (percentage)
 * - Period High
 * - Period Low
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.metrics - Metrics object from getPerformanceRangeMetrics()
 * @param {boolean} [props.showCurrentValue=true] - Whether to display current value metric
 * @param {number} props.metrics.currentValue - Current portfolio value
 * @param {number} props.metrics.periodChange - Change amount for period
 * @param {number|null} props.metrics.periodRoi - Return percentage for period
 * @param {number} props.metrics.periodHigh - Highest value in period
 * @param {number} props.metrics.periodLow - Lowest value in period
 */
export default function PortfolioMetricsRow({
  metrics = {},
  showCurrentValue = true,
  title = "Based on active range",
  includeDelta = true,
  includeRangeExtremes = true,
  containerClassName = "mt-6",
  extraMetrics = [],
}) {
  const {
    currentValue = 0,
    periodChange = 0,
    periodRoi = null,
    periodHigh = 0,
    periodLow = 0,
  } = metrics;

  const periodChangeClass = periodChange >= 0 ? "metric-positive" : "metric-negative";
  const periodRoiClass = (periodRoi ?? 0) >= 0 ? "metric-positive" : "metric-negative";
  const safeExtraMetrics = Array.isArray(extraMetrics) ? extraMetrics : [];

  const metricBlocks = [
    ...(showCurrentValue
      ? [{
          key: "current-value",
          label: "Current Value",
          value: currencyFormatter.format(currentValue),
          toneClassName: "text-[var(--text-primary)]",
        }]
      : []),
    ...(includeDelta
      ? [
          {
            key: "period-change",
            label: "Period Change",
            value: formatSignedCurrency(periodChange),
            toneClassName: periodChangeClass,
          },
          {
            key: "period-return",
            label: "Period Return",
            value: formatPercent(periodRoi),
            toneClassName: periodRoiClass,
          },
        ]
      : []),
    ...(includeRangeExtremes
      ? [
          {
            key: "period-high",
            label: "Period High",
            value: currencyFormatter.format(periodHigh),
            toneClassName: "text-[var(--text-primary)]",
          },
          {
            key: "period-low",
            label: "Period Low",
            value: currencyFormatter.format(periodLow),
            toneClassName: "text-[var(--text-primary)]",
          },
        ]
      : []),
    ...safeExtraMetrics.map((metric, index) => ({
      key: metric?.key || `extra-metric-${index}`,
      label: metric?.label || "Metric",
      value: String(metric?.value ?? "—"),
      toneClassName: metric?.toneClassName || "text-[var(--text-primary)]",
    })),
  ];

  return (
    <div className={containerClassName}>
      <p className="mb-4 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)]">
        {title}
      </p>
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 lg:grid-cols-4">
        {metricBlocks.map((metric) => (
          <div key={metric.key}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {metric.label}
            </p>
            <p className={`mt-1.5 text-lg font-semibold ${metric.toneClassName}`}>
              {metric.value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

PortfolioMetricsRow.propTypes = {
  metrics: PropTypes.shape({
    currentValue: PropTypes.number,
    periodChange: PropTypes.number,
    periodRoi: PropTypes.number,
    periodHigh: PropTypes.number,
    periodLow: PropTypes.number,
  }),
  showCurrentValue: PropTypes.bool,
  title: PropTypes.string,
  includeDelta: PropTypes.bool,
  includeRangeExtremes: PropTypes.bool,
  containerClassName: PropTypes.string,
  extraMetrics: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string,
      label: PropTypes.string,
      value: PropTypes.string,
      toneClassName: PropTypes.string,
    })
  ),
};
