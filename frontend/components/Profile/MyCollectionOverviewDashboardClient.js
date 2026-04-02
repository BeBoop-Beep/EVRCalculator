"use client";

import { useMemo, useState } from "react";

import PortfolioOverviewComposer from "@/components/Profile/PortfolioOverviewComposer";

const DASHBOARD_DATA = {
  commandCenter: {
    totalValue: 18245.87,
    investedValue: 14980.0,
    change24hPercent: 0.91,
    change7dPercent: 4.38,
    cardsCount: 428,
    sealedCount: 37,
    wishlistCount: 64,
    lastSyncedAt: "2026-03-31T14:08:00.000Z",
    freshnessLabel: "Fresh",
  },
  performance: {
    periodLabel: "Last 7 days",
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
  insights: {
    topMovers: [
      { id: "m1", name: "Charizard ex SIR", changePercent7d: 8.7, valueLabel: "$582" },
      { id: "m2", name: "Mew ex Gold", changePercent7d: 6.1, valueLabel: "$214" },
      { id: "m3", name: "Gengar VMAX Alt", changePercent7d: -2.4, valueLabel: "$331" },
    ],
    allocationSummary: [
      { id: "a1", label: "Cards", valuePercent: 68, valueLabel: "$12.4k" },
      { id: "a2", label: "Sealed", valuePercent: 24, valueLabel: "$4.4k" },
      { id: "a3", label: "Merchandise", valuePercent: 8, valueLabel: "$1.4k" },
    ],
    concentrationText: "Top 5 assets represent 46% of total portfolio value.",
  },
  meta: {
    connectedTables: [],
    warnings: [],
    fallbackUsed: true,
  },
};

export default function MyCollectionOverviewDashboardClient({
  collectionItems = [],
}) {
  const [selectedRange, setSelectedRange] = useState("7D");

  const parseCurrentPrice = (item) => {
    const rawValue = item?.valueLabel ?? item?.estimated_value ?? 0;
    const numeric = Number(String(rawValue).replace(/[^\d.-]/g, ""));
    return Number.isFinite(numeric) ? numeric : 0;
  };

  const performanceHighlights = useMemo(() => {
    const candidates = collectionItems
      .map((item) => {
        const purchasePrice = Number(item?.purchase_price);
        if (!Number.isFinite(purchasePrice) || purchasePrice <= 0) return null;

        const currentPrice = parseCurrentPrice(item);
        const changePercent = ((currentPrice - purchasePrice) / purchasePrice) * 100;

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
  }, [collectionItems]);

  const portfolioSignals = useMemo(() => {
    const assets = collectionItems
      .map((item) => {
        const unitValue = parseCurrentPrice(item);
        const quantity = Number(item?.quantity);
        const resolvedQuantity = Number.isFinite(quantity) && quantity > 0 ? quantity : 1;
        const marketValue = unitValue * resolvedQuantity;

        return {
          id: item?.id,
          marketValue,
          isSealed: item?.collectible_type === "sealed_product" || Boolean(item?.productType),
          isSlab: Boolean(item?.gradingLabel),
        };
      })
      .filter((asset) => asset.marketValue > 0);

    const totalValue = assets.reduce((sum, asset) => sum + asset.marketValue, 0);
    const bucketValues = {
      Cards: 0,
      Sealed: 0,
      Slabs: 0,
    };
    const bucketCounts = {
      Cards: 0,
      Sealed: 0,
      Slabs: 0,
    };

    assets.forEach((asset) => {
      if (asset.isSealed) {
        bucketValues.Sealed += asset.marketValue;
        bucketCounts.Sealed += 1;
        return;
      }

      if (asset.isSlab) {
        bucketValues.Slabs += asset.marketValue;
        bucketCounts.Slabs += 1;
        return;
      }

      bucketValues.Cards += asset.marketValue;
      bucketCounts.Cards += 1;
    });

    const activeBuckets = Object.entries(bucketValues).filter(([, value]) => value > 0);
    const rawPercentages = activeBuckets.map(([label, value]) => ({
      label,
      value,
      rawPercent: totalValue > 0 ? (value / totalValue) * 100 : 0,
    }));

    const roundedPercentages = rawPercentages.map((entry) => ({
      ...entry,
      basePercent: Math.floor(entry.rawPercent),
      remainder: entry.rawPercent - Math.floor(entry.rawPercent),
    }));

    let remainingPercent = Math.max(0, 100 - roundedPercentages.reduce((sum, entry) => sum + entry.basePercent, 0));

    roundedPercentages
      .sort((a, b) => b.remainder - a.remainder)
      .forEach((entry) => {
        if (remainingPercent <= 0) return;
        entry.basePercent += 1;
        remainingPercent -= 1;
      });

    const allocationRows = roundedPercentages
      .sort((a, b) => b.value - a.value)
      .map((entry, index) => ({
        id: `allocation-${index}-${entry.label.toLowerCase()}`,
        label: entry.label,
        percent: entry.basePercent,
        count: bucketCounts[entry.label] || 0,
      }));

    const topThreeValue = assets
      .slice()
      .sort((a, b) => b.marketValue - a.marketValue)
      .slice(0, 3)
      .reduce((sum, asset) => sum + asset.marketValue, 0);

    const concentrationPercent = totalValue > 0 ? Math.round((topThreeValue / totalValue) * 100) : 0;

    return {
      allocationRows,
      concentrationPercent,
    };
  }, [collectionItems]);

  return (
    <section>
      <PortfolioOverviewComposer
        dashboardData={DASHBOARD_DATA}
        selectedRange={selectedRange}
        onRangeChange={setSelectedRange}
        performanceHighlights={performanceHighlights}
        portfolioSignals={portfolioSignals}
        mode="owner"
      />
    </section>
  );
}
