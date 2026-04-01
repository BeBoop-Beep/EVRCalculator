"use client";

import ProfileStatCard from "@/components/Profile/ProfileStatCard";
import OverviewRangeToggle from "@/components/Profile/OverviewRangeToggle";
import {
  getPerformanceRangeData,
} from "@/lib/profile/portfolioPerformanceRange";

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

const numberFormatter = new Intl.NumberFormat("en-US");
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

/**
 * Unified Portfolio Command Center
 * 
 * Hero section displaying portfolio totals, performance overview, and key metrics.
 * Adapts visual treatment based on owner vs public mode.
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.dashboardData - Dashboard data shape
 * @param {string} props.selectedRange - Currently selected time range
 * @param {Function} props.onRangeChange - Callback when time range is changed
 * @param {"owner" | "public"} [props.mode="owner"] - Rendering mode
 */
export default function PortfolioCommandCenter({ 
  dashboardData, 
  selectedRange, 
  onRangeChange,
  mode = "owner",
}) {
  const isOwnerMode = mode === "owner";
  const data = dashboardData?.commandCenter || MOCK_COMMAND_CENTER_DATA;
  const perf = getPerformanceRangeData(selectedRange, dashboardData?.performance);
  const freshnessLabel = data.freshnessLabel ?? "—";
  const isFresh = freshnessLabel.toLowerCase() === "fresh";

  return (
    <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5">
      {/* Section header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            {isOwnerMode ? "Portfolio Analytics" : "Portfolio Overview"}
          </p>
          <h2 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
            {isOwnerMode ? "Command Center" : "Portfolio Summary"}
          </h2>
        </div>
        {isOwnerMode && (
          <div className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {formatRelativeSync(data.lastSyncedAt)}
          </div>
        )}
      </div>

      {/* Primary row */}
      <div className="grid gap-3 sm:grid-cols-2">
        {/* Hero: Total Portfolio Value */}
        <div className="dashboard-panel flex flex-col rounded-2xl border border-[var(--brand)]/20 p-5">
          <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--text-secondary)]/80">Total Portfolio Value</p>
          <p className="mt-3 text-[2.75rem] font-extrabold leading-none tracking-tight text-[var(--text-primary)]">
            {currencyFormatter.format(data.totalValue)}
          </p>
          <p className="mt-2 text-sm font-medium text-[var(--text-secondary)]">Portfolio Value</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-xs text-[var(--text-secondary)]">24h</span>
            <span className={`text-sm font-semibold ${getChangeToneClass(data.change24hPercent)}`}>
              {formatPercent(data.change24hPercent)}
            </span>
            <span className="select-none text-[var(--border-subtle)]">·</span>
            <span className="text-xs text-[var(--text-secondary)]">7d</span>
            <span className={`text-sm font-semibold ${getChangeToneClass(data.change7dPercent)}`}>
              {formatPercent(data.change7dPercent)}
            </span>
          </div>
          {isOwnerMode && (
            <div className="mt-auto pt-4">
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ${
                  isFresh
                    ? "border-[var(--success)]/35 bg-[var(--success)]/12 text-[var(--success)]"
                    : "border-[var(--warning)]/35 bg-[var(--warning)]/12 text-[var(--warning)]"
                }`}
              >
                {freshnessLabel}
              </span>
            </div>
          )}
        </div>

        {/* Performance card reflecting shared dashboard range */}
        <div className="dashboard-panel flex flex-col rounded-2xl border border-[var(--border-subtle)] p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Portfolio Performance</p>
            <OverviewRangeToggle
              selectedRange={selectedRange}
              onRangeChange={onRangeChange}
              ariaLabel="Portfolio command center performance time range"
            />
          </div>
          <p className={`mt-3 text-[2.35rem] font-bold leading-none tracking-tight ${getChangeToneClass(perf.changePercent)}`}>
            {formatPercent(perf.changePercent)}
          </p>
          <p className="mt-1.5 text-sm font-medium text-[var(--text-secondary)]">
            {perf.changePercent >= 0 ? "+" : ""}
            {currencyFormatter.format(perf.changeDollar)} · {perf.range}
          </p>
          <p className="mt-auto pt-3 text-xs text-[var(--text-secondary)]">{perf.helper}</p>
        </div>
      </div>

      {/* Secondary row: compact stat cards */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <ProfileStatCard
          label="Cards"
          value={numberFormatter.format(data.cardsCount)}
          subValue="Singles tracked"
          compact
        />
        <ProfileStatCard
          label="Sealed"
          value={numberFormatter.format(data.sealedCount)}
          subValue="Products held"
          compact
        />
        <ProfileStatCard
          label="Wishlist"
          value={numberFormatter.format(data.wishlistCount)}
          subValue="Acquisition targets"
          compact
        />
        {isOwnerMode ? (
          <ProfileStatCard
            label="Price Freshness"
            value={freshnessLabel}
            subValue={formatRelativeSync(data.lastSyncedAt)}
            valueClassName="text-[1.5rem] font-medium text-[var(--text-secondary)]"
            badge="Sync"
            badgeTone="neutral"
            compact
          />
        ) : (
          <ProfileStatCard
            label="Profile Mode"
            value="Public"
            subValue="Read-only portfolio lens"
            valueClassName="text-[1.35rem] font-medium text-[var(--text-secondary)]"
            badge="Read only"
            badgeTone="neutral"
            compact
          />
        )}
      </div>
    </section>
  );
}
