import { buildCollectionAssetShowcaseSlots } from "@/lib/profile/featuredItemsModel";

function toCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function makeSeed(input) {
  return Array.from(input || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
}

function formatRelativeDate(daysAgo) {
  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo < 7) return `${daysAgo} days ago`;
  return `${Math.floor(daysAgo / 7)} weeks ago`;
}

/**
 * @typedef {import("@/types/profile").UserProfileRow} UserProfileRow
 */

/**
 * @param {{ publicProfile: UserProfileRow | null, username: string, collectionAssets?: Array<any>, enableMockFallback?: boolean }} params
 */
export function buildPublicOverviewModel({ publicProfile, username, collectionAssets = [], enableMockFallback = true }) {
  if (!publicProfile && !enableMockFallback) {
    return {
      showcase: {
        topConviction: null,
        biggestGainer: null,
        spotlight: null,
      },
      snapshotStats: [],
      performance: {
        points: [],
        periodLabel: "No history",
        valueLabel: "No value data",
        trendLabel: "No trend data",
        returnLabel: "No return data",
      },
      highlights: [],
      recentActivity: [],
    };
  }

  const seed = makeSeed(publicProfile?.username || username);
  const summary = publicProfile?.collection_summary || {};
  const collectionValue = Number.isFinite(Number(summary?.portfolio_value))
    ? Number(summary.portfolio_value)
    : 3200 + (seed % 3400);
  const trackedItems = Number.isFinite(Number(summary?.cards_count))
    ? Number(summary.cards_count)
    : 120 + (seed % 480);
  const sealedCount = Number.isFinite(Number(summary?.sealed_count)) ? Number(summary.sealed_count) : 0;
  const gradedCount = Number.isFinite(Number(summary?.graded_count)) ? Number(summary.graded_count) : 0;
  const wishlistCount = 12 + (seed % 70);
  const favoriteTcg = publicProfile?.favorite_tcg_name || "Pokemon";
  const showcase = buildCollectionAssetShowcaseSlots(collectionAssets, {
    activePeriodLabel: "30D",
  });

  return {
    showcase,
    snapshotStats: [
      {
        id: "snapshot-value",
        label: "Collection Value",
        value: toCurrency(collectionValue),
        helpText: "Estimated from public portfolio data",
      },
      {
        id: "snapshot-items",
        label: "Items Tracked",
        value: (trackedItems + sealedCount + gradedCount).toLocaleString("en-US"),
        helpText: "Public-safe cards, sealed, and graded counts",
      },
      {
        id: "snapshot-category",
        label: "Top Category",
        value: favoriteTcg,
        helpText: "Most represented TCG",
      },
      {
        id: "snapshot-wishlist",
        label: "Wishlist",
        value: wishlistCount.toLocaleString("en-US"),
        helpText: "Public wishlist entries",
      },
    ],
    performance: {
      points: [26, 34, 39, 31, 43, 56, 52, 64],
      periodLabel: "Last 8 periods",
      valueLabel: `${toCurrency(collectionValue)} current estimate`,
      trendLabel: "+8.6% over 30 days",
      returnLabel: "+24.1% all time",
    },
    highlights: [
      {
        id: "highlight-mover",
        label: "Biggest Mover",
        value: "Signature Chase +18.3%",
        context: "Best performer over the last 30 days",
      },
      {
        id: "highlight-most-valuable",
        label: "Most Valuable Asset",
        value: toCurrency(Math.round(collectionValue * 0.19)),
        context: "Top public asset by estimated value",
      },
      {
        id: "highlight-strongest-category",
        label: "Strongest Category",
        value: favoriteTcg,
        context: "Largest concentration in public showcase",
      },
      {
        id: "highlight-completion",
        label: "Collection Completion",
        value: `${52 + (seed % 31)}%`,
        context: "Placeholder metric for set-completion progress",
      },
    ],
    recentActivity: [
      {
        id: "activity-1",
        title: "Added a card to collection",
        description: "A new item was added to the public showcase.",
        timestampLabel: formatRelativeDate(1),
      },
      {
        id: "activity-2",
        title: "Updated wishlist",
        description: "Wishlist priorities were refreshed.",
        timestampLabel: formatRelativeDate(4),
      },
      {
        id: "activity-3",
        title: "Featured an item",
        description: "A portfolio highlight was promoted in the showcase.",
        timestampLabel: formatRelativeDate(9),
      },
    ],
  };
}
