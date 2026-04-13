"use client";

import { useState } from "react";
import PortfolioOverviewComposer from "@/components/Profile/PortfolioOverviewComposer";

/**
 * Public Portfolio Overview Composer
 * 
 * Wrapper component that renders the unified portfolio overview in public/read-only mode.
 * Sits within the public profile layout and provides the premium portfolio view to visitors.
 * 
 * Can be extended to include optional featured items section (above overview) 
 * and recent activity section (below overview).
 * 
 * @component
 * @param {Object} props
 * @param {Object} props.dashboardData - Unified dashboard data containing commandCenter, performance, insights
 */
export default function PublicPortfolioOverviewComposer({
  dashboardData,
  performanceHighlights = null,
  portfolioSignals = null,
}) {
  const [selectedRange, setSelectedRange] = useState("7D");

  return (
    <PortfolioOverviewComposer
      dashboardData={dashboardData}
      selectedRange={selectedRange}
      onRangeChange={setSelectedRange}
      performanceHighlights={performanceHighlights}
      portfolioSignals={portfolioSignals}
      mode="public"
    />
  );
}
