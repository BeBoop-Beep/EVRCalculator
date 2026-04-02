"use client";

/** @typedef {import("@/types/portfolioCommandCenter").PortfolioCommandCenterData} PortfolioCommandCenterData */

/** @type {PortfolioCommandCenterData} */
const MOCK_COMMAND_CENTER_DATA = {
  totalValue: 18245.87,
  change24hPercent: 0.91,
  change7dPercent: 4.38,
  cardsCount: 428,
  sealedCount: 37,
  wishlistCount: 64,
  lastSyncedAt: "2026-03-31T14:08:00.000Z",
  freshnessLabel: "Fresh",
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatPercent(percent) {
  const absolute = Math.abs(percent).toFixed(2);
  const sign = percent > 0 ? "+" : percent < 0 ? "-" : "";
  return `${sign}${absolute}%`;
}

function getChangeToneClass(percent) {
  if (percent > 0) return "metric-positive";
  if (percent < 0) return "metric-negative";
  return "text-[var(--text-primary)]";
}

function formatRelativeSync(isoString) {
  const now = Date.now();
  const syncedAt = new Date(isoString).getTime();
  if (!Number.isFinite(syncedAt)) return "No sync available";

  const minutes = Math.max(0, Math.round((now - syncedAt) / 60000));
  if (minutes < 1) return "Updated just now";
  if (minutes < 60) return `Updated ${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Updated ${hours}h ago`;

  const days = Math.round(hours / 24);
  return `Updated ${days}d ago`;
}

function getLatestPortfolioValue(performanceData) {
  const oneYearPoints = performanceData?.rangeSeries?.["1Y"]?.points;
  if (Array.isArray(oneYearPoints) && oneYearPoints.length > 0) {
    const latestOneYear = Number(oneYearPoints[oneYearPoints.length - 1]?.totalValue);
    if (Number.isFinite(latestOneYear)) {
      return latestOneYear;
    }
  }

  const sevenDayPoints = performanceData?.points;
  if (Array.isArray(sevenDayPoints) && sevenDayPoints.length > 0) {
    const latestSevenDay = Number(sevenDayPoints[sevenDayPoints.length - 1]?.totalValue);
    if (Number.isFinite(latestSevenDay)) {
      return latestSevenDay;
    }
  }

  return 0;
}

/**
 * Unified Portfolio Command Center
 * 
 * Hero section displaying portfolio totals, performance overview, and key metrics.
 * Adapts visual treatment based on owner vs public mode.
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.dashboardData - Dashboard data shape
 * @param {"owner" | "public"} [props.mode="owner"] - Rendering mode
 */
export default function PortfolioCommandCenter({ 
  dashboardData, 
  mode = "owner",
}) {
  const isOwnerMode = mode === "owner";
  const data = dashboardData?.commandCenter || MOCK_COMMAND_CENTER_DATA;
  const totalValue = Number.isFinite(Number(data.totalValue))
    ? Number(data.totalValue)
    : getLatestPortfolioValue(dashboardData?.performance);
  const parsedInvestedValue = Number(data.investedValue);
  const investedValue = Number.isFinite(parsedInvestedValue) && parsedInvestedValue > 0
    ? parsedInvestedValue
    : Math.max(0, totalValue);
  const profitLossValue = totalValue - investedValue;
  const roiPercent = investedValue > 0 ? (profitLossValue / investedValue) * 100 : 0;
  const profitLossTone = getChangeToneClass(profitLossValue);
  const roiTone = getChangeToneClass(roiPercent);

  const formatSignedCurrency = (value) => {
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${currencyFormatter.format(Math.abs(value))}`;
  };

  const kpiCards = [
    {
      key: "total",
      label: "Total Portfolio Value",
      value: currencyFormatter.format(totalValue),
      tone: "text-[var(--text-primary)]",
    },
    {
      key: "roi",
      label: "Lifetime ROI",
      value: formatPercent(roiPercent),
      tone: roiTone,
    },
    {
      key: "invested",
      label: "Total Invested",
      value: currencyFormatter.format(investedValue),
      tone: "text-[var(--text-primary)]",
    },
    {
      key: "profit",
      label: "Total Profit",
      value: formatSignedCurrency(profitLossValue),
      tone: profitLossTone,
    },
  ];

  return (
    <section className="space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Summary</p>
        {isOwnerMode && (
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
            {formatRelativeSync(data.lastSyncedAt)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {kpiCards.map((metric) => (
          <article
            key={metric.key}
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-4 py-3"
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{metric.label}</p>
            <p className={`mt-1 text-[1.1rem] font-semibold ${metric.tone}`}>{metric.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
