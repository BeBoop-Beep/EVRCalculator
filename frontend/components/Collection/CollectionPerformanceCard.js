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
  totalItems = 0,
  totalValue = "$0",
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

  const performancePercent = performanceData.changePercent || 0;
  const isPositive = performancePercent >= 0;

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
      <div className="border-t border-[var(--border-subtle)] pt-4">
        <div className="grid grid-cols-3 gap-3">
          {/* Total Items */}
          <div className="text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Total Items
            </p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {totalItems}
            </p>
          </div>

          {/* Total Value */}
          <div className="text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Total Value
            </p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {totalValue}
            </p>
          </div>

          {/* Performance % */}
          <div className="text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              Performance
            </p>
            <p className={`mt-2 text-lg font-semibold ${isPositive ? "text-[var(--metric-positive)]" : "text-[var(--metric-negative)]"}`}>
              {isPositive ? "+" : ""}{performancePercent.toFixed(2)}%
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
