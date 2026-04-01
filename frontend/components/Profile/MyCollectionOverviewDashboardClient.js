"use client";

import { useState } from "react";

import PortfolioOverviewComposer from "@/components/Profile/PortfolioOverviewComposer";

const DASHBOARD_DATA = {
  commandCenter: {
    totalValue: 18245.87,
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

export default function MyCollectionOverviewDashboardClient() {
  const [selectedRange, setSelectedRange] = useState("7D");

  return (
    <PortfolioOverviewComposer
      dashboardData={DASHBOARD_DATA}
      selectedRange={selectedRange}
      onRangeChange={setSelectedRange}
      mode="owner"
    />
  );
}
