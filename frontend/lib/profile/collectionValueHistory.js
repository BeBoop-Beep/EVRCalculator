/**
 * Collection Value History Utility
 * Generates performance data for collection values across time ranges
 * Similar to portfolio performance but scoped to filtered collections
 */

export const COLLECTION_TIME_RANGES = ["7D", "30D", "90D", "1Y", "All"];

const RANGE_TEMPLATES = {
  "7D": ["Mar 24", "Mar 25", "Mar 26", "Mar 27", "Mar 28", "Mar 29", "Mar 30", "Mar 31"],
  "30D": ["Mar 02", "Mar 08", "Mar 15", "Mar 22", "Mar 31"],
  "90D": ["Jan", "Feb", "Mar"],
  "1Y": ["Q2 25", "Q3 25", "Q4 25", "Q1 26"],
  All: ["6mo ago", "3mo ago", "1mo ago", "Now"],
};

const RANGE_GROWTH_WEIGHTS = {
  "7D": 0.18,
  "30D": 0.35,
  "90D": 0.55,
  "1Y": 0.78,
  All: 1,
};

const RANGE_PROGRESSIONS = {
  "7D": [0, 0.22, 0.41, 0.34, 0.63, 0.79, 0.88, 1],
  "30D": [0, 0.24, 0.48, 0.74, 1],
  "90D": [0, 0.46, 1],
  "1Y": [0, 0.28, 0.61, 1],
  All: [0, 0.25, 0.62, 1],
};

function parseNumericValue(value) {
  const numeric = Number(String(value ?? "").replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function getItemQuantity(item) {
  const quantity = Number(item?.quantity);
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1;
}

function getItemCurrentValue(item) {
  return parseNumericValue(item?.valueLabel ?? item?.estimated_value) * getItemQuantity(item);
}

function getItemInvestedValue(item) {
  const explicitCostBasis = Number(item?.cost_basis ?? item?.purchase_price);
  if (Number.isFinite(explicitCostBasis) && explicitCostBasis > 0) {
    return explicitCostBasis * getItemQuantity(item);
  }

  const currentValue = getItemCurrentValue(item);
  return currentValue > 0 ? currentValue * 0.84 : 0;
}

function buildRangeSeries(rangeKey, currentValue, investedValue, itemCount) {
  const labels = RANGE_TEMPLATES[rangeKey] || RANGE_TEMPLATES["7D"];
  const growthWeight = RANGE_GROWTH_WEIGHTS[rangeKey] ?? RANGE_GROWTH_WEIGHTS["7D"];
  const progressions = RANGE_PROGRESSIONS[rangeKey] || RANGE_PROGRESSIONS["7D"];
  const totalGain = currentValue - investedValue;
  const startValue = Math.max(0, currentValue - (totalGain * growthWeight));
  const curveAmplitude = Math.min(currentValue * 0.035, Math.max(12, itemCount * 9));

  return labels.map((dateLabel, index) => {
    const progress = progressions[index] ?? (labels.length === 1 ? 1 : index / (labels.length - 1));
    const phase = labels.length === 1 ? 0 : index / (labels.length - 1);
    const oscillation = Math.sin(phase * Math.PI * 2) * curveAmplitude * (1 - progress) * 0.35;
    const totalValue = Math.max(0, Math.round(startValue + ((currentValue - startValue) * progress) + oscillation));

    return {
      dateLabel,
      totalValue,
    };
  });
}

function resolveCustomCollectionPoints(collectionData, selectedRange) {
  if (!collectionData) return null;

  if (Array.isArray(collectionData?.points)) {
    return collectionData.points;
  }

  if (Array.isArray(collectionData?.ranges?.[selectedRange])) {
    return collectionData.ranges[selectedRange];
  }

  if (Array.isArray(collectionData?.[selectedRange])) {
    return collectionData[selectedRange];
  }

  return null;
}

/**
 * Generate mock collection value history
 * In production, this would come from your backend API
 */
function generateCollectionHistory(tcg = "All", timeRange = "7D") {
  // These would typically come from your database
  // For now, generating representative data
  const baseValues = {
    All: {
      "7D": [
        { dateLabel: "Mar 24", totalValue: 1520 },
        { dateLabel: "Mar 25", totalValue: 1585 },
        { dateLabel: "Mar 26", totalValue: 1640 },
        { dateLabel: "Mar 27", totalValue: 1530 },
        { dateLabel: "Mar 28", totalValue: 1725 },
        { dateLabel: "Mar 29", totalValue: 1880 },
        { dateLabel: "Mar 30", totalValue: 1970 },
        { dateLabel: "Mar 31", totalValue: 2245 },
      ],
      "30D": [
        { dateLabel: "Mar 02", totalValue: 1200 },
        { dateLabel: "Mar 08", totalValue: 1340 },
        { dateLabel: "Mar 15", totalValue: 1580 },
        { dateLabel: "Mar 22", totalValue: 1850 },
        { dateLabel: "Mar 31", totalValue: 2245 },
      ],
      "90D": [
        { dateLabel: "Jan", totalValue: 980 },
        { dateLabel: "Feb", totalValue: 1340 },
        { dateLabel: "Mar", totalValue: 2245 },
      ],
      "1Y": [
        { dateLabel: "Q2 25", totalValue: 520 },
        { dateLabel: "Q3 25", totalValue: 780 },
        { dateLabel: "Q4 25", totalValue: 1120 },
        { dateLabel: "Q1 26", totalValue: 2245 },
      ],
      All: [
        { dateLabel: "6mo ago", totalValue: 450 },
        { dateLabel: "3mo ago", totalValue: 680 },
        { dateLabel: "1mo ago", totalValue: 1200 },
        { dateLabel: "Now", totalValue: 2245 },
      ],
    },
    Pokemon: {
      "7D": [
        { dateLabel: "Mar 24", totalValue: 1220 },
        { dateLabel: "Mar 25", totalValue: 1285 },
        { dateLabel: "Mar 26", totalValue: 1340 },
        { dateLabel: "Mar 27", totalValue: 1230 },
        { dateLabel: "Mar 28", totalValue: 1425 },
        { dateLabel: "Mar 29", totalValue: 1580 },
        { dateLabel: "Mar 30", totalValue: 1770 },
        { dateLabel: "Mar 31", totalValue: 1945 },
      ],
      "30D": [
        { dateLabel: "Mar 02", totalValue: 950 },
        { dateLabel: "Mar 08", totalValue: 1050 },
        { dateLabel: "Mar 15", totalValue: 1280 },
        { dateLabel: "Mar 22", totalValue: 1550 },
        { dateLabel: "Mar 31", totalValue: 1945 },
      ],
      "90D": [
        { dateLabel: "Jan", totalValue: 750 },
        { dateLabel: "Feb", totalValue: 1040 },
        { dateLabel: "Mar", totalValue: 1945 },
      ],
      "1Y": [
        { dateLabel: "Q2 25", totalValue: 380 },
        { dateLabel: "Q3 25", totalValue: 580 },
        { dateLabel: "Q4 25", totalValue: 920 },
        { dateLabel: "Q1 26", totalValue: 1945 },
      ],
      All: [
        { dateLabel: "6mo ago", totalValue: 320 },
        { dateLabel: "3mo ago", totalValue: 480 },
        { dateLabel: "1mo ago", totalValue: 950 },
        { dateLabel: "Now", totalValue: 1945 },
      ],
    },
  };

  const tcgKey = baseValues[tcg] ? tcg : "All";
  const rangeKey = baseValues[tcgKey][timeRange] ? timeRange : "7D";
  return baseValues[tcgKey][rangeKey];
}

export function buildCollectionValueHistoryFromItems(items = []) {
  const safeItems = Array.isArray(items) ? items : [];
  const currentValue = safeItems.reduce((sum, item) => sum + getItemCurrentValue(item), 0);
  const investedValue = safeItems.reduce((sum, item) => sum + getItemInvestedValue(item), 0);

  return {
    ranges: COLLECTION_TIME_RANGES.reduce((accumulator, rangeKey) => ({
      ...accumulator,
      [rangeKey]: buildRangeSeries(rangeKey, currentValue, investedValue, safeItems.length),
    }), {}),
  };
}

/**
 * Get collection value data for a specific TCG and time range
 * @param {string} selectedRange - Time range (7D, 30D, 90D, 1Y, All)
 * @param {string} tcg - TCG name (All, Pokemon, etc.)
 * @param {Object} collectionData - Optional override collection data
 * @returns {Object} - Performance data with calculations
 */
export function getCollectionValueData(selectedRange, tcg = "All", collectionData = null) {
  const validRange = COLLECTION_TIME_RANGES.includes(selectedRange) ? selectedRange : "7D";
  const validTCG = tcg || "All";

  // Use provided data or generate mock data
  const points = resolveCustomCollectionPoints(collectionData, validRange) || generateCollectionHistory(validTCG, validRange);

  const currentValue = points[points.length - 1]?.totalValue || 0;
  const startValue = points[0]?.totalValue || 0;
  const changeDollar = currentValue - startValue;
  const changePercent = startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0;

  const helpers = {
    "7D": "Recent collection activity over the past week",
    "30D": "Collection performance tracked over 30 days",
    "90D": "Quarterly collection value trend",
    "1Y": "Year-to-date collection performance",
    All: "Historical collection performance since first entry",
  };

  return {
    range: validRange,
    tcg: validTCG,
    helper: helpers[validRange],
    points,
    currentValue,
    changeDollar,
    changePercent,
  };
}

/**
 * Filter collection items by TCG
 * @param {Array} items - Collection items
 * @param {string} tcg - TCG filter (All or specific TCG name)
 * @returns {Array} - Filtered items
 */
export function filterCollectionByTCG(items, tcg = "All") {
  if (tcg === "All") return items;
  
  return items.filter((item) => {
    // Determine TCG from item properties
    const itemTCG = item.set?.toLowerCase() || "";
    return itemTCG.includes(tcg.toLowerCase());
  });
}

/**
 * Get available TCGs from collection
 * @param {Array} items - Collection items
 * @returns {Array} - List of unique TCGs found in collection
 */
export function getAvailableTCGs(items) {
  const tcgs = new Set(["All"]); // Always include "All"
  
  items.forEach((item) => {
    if (item.set) {
      // Extract TCG from set name (e.g., "Scarlet & Violet" -> "Pokemon")
      // This is simplified; adjust based on your actual set naming
      if (item.set.includes("Scarlet") || item.set.includes("Violet") || item.set.includes("Base Set")) {
        tcgs.add("Pokemon");
      }
    }
  });

  return Array.from(tcgs);
}
