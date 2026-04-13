/**
 * Collection Asset Showcase Slot Model
 *
 * Explicit 3-slot contract used by both My Collection (owner) and Public Profile (read-only):
 *  - topConviction: auto-derived from largest allocation share
 *  - spotlight: user-selected asset with deterministic fallback
 *  - biggestGainer: auto-derived from strongest gain signal
 */

export const SHOWCASE_ASSET_SLOT_CONFIG = Object.freeze([
  {
    key: "topConviction",
    label: "Top Conviction Hold",
    mode: "computed",
    icon: "TC",
  },
  {
    key: "spotlight",
    label: "Spotlight Asset",
    mode: "manual",
    icon: "SP",
  },
  {
    key: "biggestGainer",
    label: "Biggest Gainer",
    mode: "computed",
    icon: "BG",
  },
]);

// Backward-compatible alias while consumers migrate.
export const SHOWCASE_SLOT_CONFIG = SHOWCASE_ASSET_SLOT_CONFIG;

const SLOT_BY_KEY = SHOWCASE_ASSET_SLOT_CONFIG.reduce((acc, slot) => {
  acc[slot.key] = slot;
  return acc;
}, {});

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function formatPercent(value, digits = 1) {
  if (!Number.isFinite(value)) return null;
  return `${value.toFixed(digits)}%`;
}

function formatCurrency(value) {
  if (!Number.isFinite(value)) return null;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function getAssetValue(asset) {
  if (!asset) return 0;
  return parseCurrencyValue(asset.valueLabel ?? asset.estimated_value ?? asset.currentValue ?? 0);
}

function parsePercent(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;

  const numeric = Number(String(value).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : null;
}

function toSpotlightCandidate(asset, fallbackSource = null) {
  if (!asset) return null;

  return {
    ...asset,
    spotlightFallbackSource: fallbackSource,
  };
}

function deriveSpotlightAsset(collectionAssets, spotlightAssetId, topConvictionAsset) {
  if (!Array.isArray(collectionAssets) || collectionAssets.length === 0) {
    return null;
  }

  if (spotlightAssetId) {
    const selected = collectionAssets.find((asset) => String(asset.id) === String(spotlightAssetId));
    if (selected) {
      return toSpotlightCandidate(selected, null);
    }
  }

  if (topConvictionAsset) {
    return toSpotlightCandidate(topConvictionAsset, "Top Conviction Hold");
  }

  const withDates = collectionAssets
    .filter((asset) => asset.acquisition_date)
    .sort((a, b) => new Date(b.acquisition_date).getTime() - new Date(a.acquisition_date).getTime());

  if (withDates.length > 0) {
    return toSpotlightCandidate(withDates[0], "Recently Added");
  }

  return toSpotlightCandidate(collectionAssets[0], "First Eligible Asset");
}

function decorateSlotAsset(slotKey, asset, meta = {}) {
  if (!asset) return null;

  const slot = SLOT_BY_KEY[slotKey];
  return {
    ...asset,
    slotKey,
    category: slot?.label || slotKey,
    categoryIcon: slot?.icon || "•",
    slotMode: slot?.mode || "computed",
    ...meta,
  };
}

/**
 * Builds explicit showcase slots from collection assets and optional spotlight selection.
 *
 * @param {array} collectionAssets
 * @param {{ spotlightAssetId?: string | null, spotlightItemId?: string | null }} [options]
 */
export function buildCollectionAssetShowcaseSlots(collectionAssets = [], options = {}) {
  const spotlightAssetId = options?.spotlightAssetId || options?.spotlightItemId || null;
  const activePeriodLabel = options?.activePeriodLabel || "Active period";

  if (!collectionAssets || collectionAssets.length === 0) {
    return {
      topConviction: null,
      biggestGainer: null,
      spotlight: null,
    };
  }

  const totalValue = collectionAssets.reduce((sum, asset) => sum + getAssetValue(asset), 0);

  // Computed slot: largest portfolio concentration by value.
  const topConviction = collectionAssets.reduce((max, asset) => {
    const itemValue = getAssetValue(asset);
    const maxValue = getAssetValue(max);
    return itemValue > maxValue ? asset : max;
  });

  const topConvictionValue = getAssetValue(topConviction);
  const topConvictionAllocation = totalValue > 0 ? (topConvictionValue / totalValue) * 100 : null;

  // Computed slot: strongest gain from active-period data when available.
  const withPerformance = collectionAssets
    .map((asset) => ({
      asset,
      change: parsePercent(
        asset.changePercentActive
          ?? asset.changePercentSelectedRange
          ?? asset.changePercent7d
          ?? asset.changePercent30d
          ?? asset.performanceChangePercent
          ?? asset.roi,
      ),
    }))
    .filter((entry) => entry.change !== null);

  let biggestGainer = withPerformance.length
    ? withPerformance.sort((a, b) => b.change - a.change)[0].asset
    : null;

  // Graceful fallback when item-level performance is unavailable.
  if (!biggestGainer && collectionAssets.length > 0) {
    const sortedByValue = [...collectionAssets].sort((a, b) => {
      const aVal = getAssetValue(a);
      const bVal = getAssetValue(b);
      return bVal - aVal;
    });
    biggestGainer = sortedByValue[1] || sortedByValue[0] || null;
  }

  // Manual slot: user-selected spotlight asset, then deterministic fallback chain.
  const spotlight = deriveSpotlightAsset(collectionAssets, spotlightAssetId, topConviction);

  const topConvictionDecorated = decorateSlotAsset("topConviction", topConviction, {
    isComputed: true,
    allocationPercent: topConvictionAllocation,
    allocationLabel: formatPercent(topConvictionAllocation),
    currentValue: topConvictionValue,
    currentValueLabel: topConviction.valueLabel ?? formatCurrency(topConvictionValue),
    metricLabel: "Allocation",
    metricValueLabel: formatPercent(topConvictionAllocation),
    statLine: topConviction.valueLabel ? `Current value ${topConviction.valueLabel}` : null,
  });

  const topGainerChange = withPerformance.find((entry) => String(entry.asset?.id) === String(biggestGainer?.id))?.change ?? null;

  const biggestGainerDecorated = decorateSlotAsset("biggestGainer", biggestGainer, {
    isComputed: true,
    hasPerformanceData: withPerformance.length > 0,
    gainPercent: topGainerChange,
    gainPercentLabel: formatPercent(topGainerChange),
    metricLabel: activePeriodLabel,
    metricValueLabel: formatPercent(topGainerChange),
    statLine: biggestGainer?.valueLabel ? `Current value ${biggestGainer.valueLabel}` : null,
  });

  return {
    topConviction: topConvictionDecorated,
    biggestGainer: biggestGainerDecorated,
    spotlight: decorateSlotAsset("spotlight", spotlight, {
      isComputed: false,
      isUserSelected: Boolean(spotlightAssetId) && String(spotlight?.id) === String(spotlightAssetId),
      usedFallback: Boolean(!spotlightAssetId || String(spotlight?.id) !== String(spotlightAssetId)),
      metricLabel: "Highlight",
      metricValueLabel: "Collector spotlight",
      statLine: spotlight?.isUserSelected
        ? "Owner-selected showcase asset"
        : spotlight?.spotlightFallbackSource
          ? `Fallback source: ${spotlight.spotlightFallbackSource}`
          : "Collector spotlight",
    }),
  };
}

/**
 * Validate if an asset can be the spotlight asset.
 * (Currently: any collection asset is valid; expandable for future rules)
 */
export function isValidSpotlightAsset(asset) {
  return asset && asset.id;
}

