"use client";

import { useMemo, useState } from "react";
import CollectionValueChart from "@/components/Collection/CollectionValueChart";
import OverviewRangeToggle from "@/components/Profile/OverviewRangeToggle";
import { getCollectionValueData } from "@/lib/profile/collectionValueHistory";

/**
 * Collection Performance Card
 * Wrapper component that displays collection value chart with time range selection
 * Allows viewing performance across different time periods for the selected TCG/scope
 * Includes integrated metrics for Total Items, Total Value, and Performance %
 * 
 * @component
 * @param {Object} props
 * @param {string} [props.initialRange="7D"] - Initial time range (7D, 30D, 90D, 1Y, All)
 * @param {string} [props.tcg="All"] - TCG filter (All, Pokemon, etc.)
 * @param {Object} [props.valueHistory] - Optional custom value history data
 * @param {Function} [props.onRangeChange] - Callback when range changes
 * @param {number} [props.totalItems=0] - Total number of items in collection
 * @param {string} [props.totalValue="$0"] - Total value of collection
 */
export default function CollectionPerformanceCard({
  initialRange = "7D",
  tcg = "All",
  valueHistory = null,
  onRangeChange = null,
  totalValue = "$0",
  investedValue = null,
  showSummaryMetrics = true,
}) {
  const [selectedRange, setSelectedRange] = useState(initialRange);

  const handleRangeChange = (newRange) => {
    setSelectedRange(newRange);
    onRangeChange?.(newRange);
  };

  // Compute performance data for the selected range
  const performanceData = useMemo(() => {
    return getCollectionValueData(selectedRange, tcg, valueHistory);
  }, [selectedRange, tcg, valueHistory]);

  const parseCurrencyLabel = (value) => {
    const numeric = Number(String(value || "").replace(/[^\d.-]/g, ""));
    return Number.isFinite(numeric) ? numeric : 0;
  };

  const currentValue = parseCurrencyLabel(totalValue) || performanceData.currentValue || 0;
  const parsedInvested = Number(
    typeof investedValue === "string"
      ? String(investedValue).replace(/[^\d.-]/g, "")
      : investedValue
  );
  const resolvedInvested = Number.isFinite(parsedInvested) && parsedInvested > 0
    ? parsedInvested
    : Math.max(0, currentValue - (performanceData.changeDollar || 0));
  const profitLoss = currentValue - resolvedInvested;
  const roiPercent = resolvedInvested > 0
    ? ((currentValue - resolvedInvested) / resolvedInvested) * 100
    : 0;

  const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

  const formatSignedCurrency = (value) => {
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${currencyFormatter.format(Math.abs(value))}`;
  };

  const formatSignedPercent = (value) => {
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${Math.abs(value).toFixed(2)}%`;
  };

  const profitClass = profitLoss >= 0 ? "text-[var(--metric-positive)]" : "text-[var(--metric-negative)]";
  const roiClass = roiPercent >= 0 ? "text-[var(--metric-positive)]" : "text-[var(--metric-negative)]";

  return (
    <section className="dashboard-panel flex flex-col rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 sm:p-5">
      {/* Header with Title and Range Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-[var(--border-subtle)]">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            Collection Performance
          </p>
        </div>
        <OverviewRangeToggle
          selectedRange={selectedRange}
          onRangeChange={handleRangeChange}
          ariaLabel="Collection performance time range"
        />
      </div>

      {/* Chart Area */}
      <div className="mt-4 mb-4">
        <CollectionValueChart
          selectedRange={selectedRange}
          tcg={tcg}
          valueHistory={valueHistory}
        />
      </div>

      {/* Integrated Metrics Footer */}
      {showSummaryMetrics ? (
        <div className="border-t border-[var(--border-subtle)] pt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Collection Value</p>
              <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{currencyFormatter.format(currentValue)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Collection Invested</p>
              <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{currencyFormatter.format(resolvedInvested)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Collection Profit/Loss</p>
              <p className={`mt-2 text-lg font-semibold ${profitClass}`}>{formatSignedCurrency(profitLoss)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Collection ROI</p>
              <p className={`mt-2 text-lg font-semibold ${roiClass}`}>{formatSignedPercent(roiPercent)}</p>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
