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
 * @param {{ publicProfile: UserProfileRow | null, username: string, enableMockFallback?: boolean }} params
 */
export function buildPublicOverviewModel({ publicProfile, username, enableMockFallback = true }) {
  if (!publicProfile && !enableMockFallback) {
    return {
      featuredItems: [],
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
  const collectionValue = 3200 + (seed % 3400);
  const trackedItems = 120 + (seed % 480);
  const wishlistCount = 12 + (seed % 70);
  const favoriteTcg = publicProfile?.favorite_tcg_name || "Pokemon";

  return {
    featuredItems: [
      {
        id: "featured-1",
        name: "Signature Chase",
        context: `${favoriteTcg} showcase item`,
        valueLabel: toCurrency(Math.round(collectionValue * 0.19)),
        imageUrl: null,
      },
      {
        id: "featured-2",
        name: "High Conviction Hold",
        context: "Long-term portfolio anchor",
        valueLabel: toCurrency(Math.round(collectionValue * 0.13)),
        imageUrl: null,
      },
      {
        id: "featured-3",
        name: "Recent Add",
        context: "Recently added to featured shelf",
        valueLabel: toCurrency(Math.round(collectionValue * 0.07)),
        imageUrl: null,
      },
    ],
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
        value: trackedItems.toLocaleString("en-US"),
        helpText: "Singles and sealed products",
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
        label: "Most Valuable Item",
        value: toCurrency(Math.round(collectionValue * 0.19)),
        context: "Top public item by estimated value",
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
