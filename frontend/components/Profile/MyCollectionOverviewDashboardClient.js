"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import PortfolioOverviewComposer from "@/components/Profile/PortfolioOverviewComposer";
import CollectionFeaturedHighlight from "@/components/Profile/CollectionFeaturedHighlight";
import { buildCollectionAssetShowcaseSlots } from "@/lib/profile/featuredItemsModel";

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

export default function MyCollectionOverviewDashboardClient({
  collectionItems = [],
  initialSpotlightAssetId = null,
}) {
  const router = useRouter();
  const [selectedRange, setSelectedRange] = useState("7D");
  const spotlightAssetId = initialSpotlightAssetId;

  const showcase = useMemo(
    () => buildCollectionAssetShowcaseSlots(collectionItems, {
      spotlightAssetId,
      activePeriodLabel: selectedRange,
    }),
    [collectionItems, spotlightAssetId, selectedRange],
  );

  const handleSpotlightEdit = () => {
    router.push("/account-settings#spotlight-asset");
  };

  const handleAddCard = () => {
    router.push("/cards");
  };

  const handleAddSealedProduct = () => {
    router.push("/products");
  };

  const handleImportCollection = () => {
    router.push("/my-portfolio");
  };

  useEffect(() => {
    const isTypingTarget = (element) => {
      if (!element || !(element instanceof HTMLElement)) return false;

      const tagName = element.tagName?.toLowerCase();
      if (tagName === "input" || tagName === "textarea") {
        return true;
      }

      return element.isContentEditable || Boolean(element.closest("[contenteditable='true']"));
    };

    const handleKeyDown = (event) => {
      if (event.defaultPrevented || event.repeat) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (String(event.key).toLowerCase() !== "a") return;
      if (isTypingTarget(document.activeElement)) return;

      event.preventDefault();
      handleAddCard();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <section className="space-y-5">
      {/* Portfolio Analytics - PRIMARY DATA FOCUS */}
      <PortfolioOverviewComposer
        dashboardData={DASHBOARD_DATA}
        selectedRange={selectedRange}
        onRangeChange={setSelectedRange}
        mode="owner"
        onAddCard={handleAddCard}
        onAddSealedProduct={handleAddSealedProduct}
        onImportCollection={handleImportCollection}
      />

      {/* Showcase Slots - SECONDARY UTILITY */}
      <CollectionFeaturedHighlight
        showcase={showcase}
        mode="owner"
        title="Portfolio Showcase"
        subtitle="Top Conviction Hold and Biggest Gainer are computed from current portfolio data. Spotlight stays owner-controlled."
        onSpotlightEdit={handleSpotlightEdit}
      />
    </section>
  );
}
