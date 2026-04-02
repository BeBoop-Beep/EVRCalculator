/**
 * Collection Value History Utility
 * Generates performance data for collection values across time ranges
 * Similar to portfolio performance but scoped to filtered collections
 */

export const COLLECTION_TIME_RANGES = ["7D", "30D", "90D", "1Y", "All"];

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
  const points = collectionData?.points || generateCollectionHistory(validTCG, validRange);

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
