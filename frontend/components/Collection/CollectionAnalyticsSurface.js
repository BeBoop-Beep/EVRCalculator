"use client";

import { useMemo, useState } from "react";

import CollectionPerformanceCard from "@/components/Collection/CollectionPerformanceCard";
import PortfolioSignalsRail from "@/components/Profile/PortfolioSignalsRail";
import { buildCollectionValueHistoryFromItems } from "@/lib/profile/collectionValueHistory";

function parseCurrencyValue(value) {
  const numeric = Number(String(value ?? "").replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function getItemQuantity(item) {
  const quantity = Number(item?.quantity);
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1;
}

function getItemCostBasis(item) {
  const explicitCostBasis = Number(item?.cost_basis ?? item?.purchase_price);
  if (Number.isFinite(explicitCostBasis) && explicitCostBasis > 0) {
    return explicitCostBasis * getItemQuantity(item);
  }

  const currentValue = parseCurrencyValue(item?.valueLabel ?? item?.estimated_value) * getItemQuantity(item);
  return currentValue > 0 ? currentValue * 0.84 : 0;
}

function getItemMarketValue(item) {
  return parseCurrencyValue(item?.valueLabel ?? item?.estimated_value) * getItemQuantity(item);
}

function getAllocationBucket(item) {
  if (item?.collectible_type === "sealed_product" || item?.productType) {
    return "Sealed";
  }

  if (item?.collectible_type === "merchandise") {
    return "Merchandise";
  }

  if (item?.gradingLabel) {
    return "Slabs";
  }

  return "Cards";
}

export default function CollectionAnalyticsSurface({
  items = [],
  initialRange = "7D",
  totalValue = "$0",
  investedValue = "$0",
}) {
  const [selectedRange, setSelectedRange] = useState(initialRange);

  const valueHistory = useMemo(() => buildCollectionValueHistoryFromItems(items), [items]);

  const performanceHighlights = useMemo(() => {
    const candidates = items
      .map((item) => {
        const costBasis = getItemCostBasis(item);
        if (costBasis <= 0) return null;

        const marketValue = getItemMarketValue(item);
        const changePercent = ((marketValue - costBasis) / costBasis) * 100;

        return {
          id: item?.id,
          name: item?.name || "Unknown item",
          changePercent,
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.changePercent - a.changePercent);

    if (candidates.length === 0) {
      return null;
    }

    return {
      bestPerformer: candidates[0],
      worstPerformer: candidates[candidates.length - 1],
    };
  }, [items]);

  const portfolioSignals = useMemo(() => {
    const assets = items
      .map((item) => ({
        id: item?.id,
        bucket: getAllocationBucket(item),
        marketValue: getItemMarketValue(item),
      }))
      .filter((asset) => asset.marketValue > 0);

    const totalMarketValue = assets.reduce((sum, asset) => sum + asset.marketValue, 0);
    const bucketValues = new Map();
    const bucketCounts = new Map();

    assets.forEach((asset) => {
      bucketValues.set(asset.bucket, (bucketValues.get(asset.bucket) || 0) + asset.marketValue);
      bucketCounts.set(asset.bucket, (bucketCounts.get(asset.bucket) || 0) + 1);
    });

    const rawRows = Array.from(bucketValues.entries())
      .map(([label, value]) => ({
        label,
        value,
        rawPercent: totalMarketValue > 0 ? (value / totalMarketValue) * 100 : 0,
      }))
      .sort((a, b) => b.value - a.value);

    const roundedRows = rawRows.map((row) => ({
      ...row,
      basePercent: Math.floor(row.rawPercent),
      remainder: row.rawPercent - Math.floor(row.rawPercent),
    }));

    let remainderBudget = Math.max(0, 100 - roundedRows.reduce((sum, row) => sum + row.basePercent, 0));
    roundedRows
      .slice()
      .sort((a, b) => b.remainder - a.remainder)
      .forEach((row) => {
        if (remainderBudget <= 0) return;
        row.basePercent += 1;
        remainderBudget -= 1;
      });

    const allocationRows = roundedRows.map((row, index) => ({
      id: `collection-allocation-${index}-${row.label.toLowerCase()}`,
      label: row.label,
      percent: row.basePercent,
      count: bucketCounts.get(row.label) || 0,
    }));

    const topThreeValue = assets
      .slice()
      .sort((a, b) => b.marketValue - a.marketValue)
      .slice(0, 3)
      .reduce((sum, asset) => sum + asset.marketValue, 0);

    return {
      allocationRows,
      concentrationPercent: totalMarketValue > 0 ? Math.round((topThreeValue / totalMarketValue) * 100) : 0,
    };
  }, [items]);

  return (
    <section className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(16rem,3fr)] xl:items-stretch xl:gap-4">
      <div className="h-full min-w-0">
        <CollectionPerformanceCard
          selectedRange={selectedRange}
          onRangeChange={setSelectedRange}
          valueHistory={valueHistory}
          totalValue={totalValue}
          investedValue={investedValue}
        />
      </div>

      <aside className="flex h-full min-w-0 flex-col space-y-2.5 xl:pt-1">
        <PortfolioSignalsRail
          performanceHighlights={performanceHighlights}
          selectedRange={selectedRange}
          portfolioSignals={portfolioSignals}
        />
      </aside>
    </section>
  );
}