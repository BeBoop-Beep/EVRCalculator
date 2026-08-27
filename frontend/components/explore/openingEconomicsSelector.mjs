/**
 * Read-only selectors for the published opening-economics contract.
 *
 * WHAT THIS IS
 * ------------
 * Field reads and display formatting for values the backend has ALREADY
 * finalized against the canonical RIP Stats snapshot. Pure: no React, no fetch,
 * no arithmetic that could produce a statistic.
 *
 * WHAT THIS DELIBERATELY IS NOT
 * -----------------------------
 * * NOT a calculator. Typical Opening and Typical Retention are pooled
 *   quantiles over 22,000,000 exact simulated outcomes. They cannot be
 *   reconstructed here, and nothing in this module may average per-set medians,
 *   average per-set ratios, or infer a median from a mean. Averaging the 22 set
 *   medians yields $1.92; the true pooled P50 is $1.84, and the difference is
 *   the whole reason this contract is published rather than derived.
 * * NOT a score. Sorting an era table is presentation order only. No rank, tier
 *   or score is assigned to an era anywhere.
 *
 * MISSING VALUES STAY MISSING
 * ---------------------------
 * Every formatter returns `null` for an absent or non-finite input so the view
 * can render the unavailable state. A fabricated `$0.00` or `0%` is
 * indistinguishable from a measured one, which makes it the more dangerous
 * failure.
 */

export const UNAVAILABLE_LABEL = "Unavailable";

function finite(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  // `Number("")` and `Number("   ")` are 0, so an empty field would otherwise
  // render as a measured $0.00 - the exact fabrication this module exists to
  // prevent. Booleans are rejected for the same reason: `Number(true)` is 1.
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function money(value, { decimals = 2 } = {}) {
  const parsed = finite(value);
  if (parsed === null) return null;
  const sign = parsed < 0 ? "-" : "";
  return `${sign}$${Math.abs(parsed).toFixed(decimals)}`;
}

/** A published RATIO (0.4543) rendered as a percentage ("45.4%"). */
export function ratioAsPercent(value, { decimals = 1 } = {}) {
  const parsed = finite(value);
  if (parsed === null) return null;
  return `${(parsed * 100).toFixed(decimals)}%`;
}

/**
 * Cents of modeled gross card value returned per $1 of pack spend.
 *
 * Presentation of the SAME published ratio, not a second statistic — which is
 * why it is derived here rather than published as its own field.
 */
export function centsPerDollar(ratio) {
  const parsed = finite(ratio);
  if (parsed === null) return null;
  return Math.round(parsed * 100);
}

export function isAvailable(economics) {
  return Boolean(economics && economics.status === "available" && economics.global);
}

/** The six-point ladder as ordered rows, or `null` when the scope has none. */
export function distributionRows(distribution, formatter) {
  if (!distribution) return null;
  const keys = ["p05", "p25", "p50", "p75", "p95", "p99"];
  const rows = keys.map((key) => ({
    key,
    label: key.toUpperCase(),
    raw: finite(distribution[key]),
    display: formatter(distribution[key]),
  }));
  return rows.some((row) => row.raw !== null) ? rows : null;
}

/**
 * The Overall headline tiles, in the fixed priority order the mobile layout
 * also relies on: the four primary metrics lead so a narrow screen shows them
 * first without a second ordering living in the component.
 */
export function headlineMetrics(scope) {
  if (!scope) return [];
  return [
    {
      key: "modeledReturn",
      label: "Modeled Return on Spend",
      value: ratioAsPercent(scope.modeledReturnOnSpend),
      help: "Long-run modeled gross card-market value relative to the current cost of one loose pack from each participating set.",
      primary: true,
    },
    {
      key: "entertainmentCost",
      label: "Average Entertainment Cost",
      value: money(scope.expectedEntertainmentCost),
      secondary: (() => {
        const share = ratioAsPercent(scope.entertainmentCostShare);
        return share === null ? null : `${share} of pack spend`;
      })(),
      suffix: "/ pack",
      help: "The difference between a product's current purchase price and the model's long-run Expected Value of its contents.",
      primary: true,
    },
    {
      key: "typicalOpening",
      label: "Typical Opening",
      value: money(scope.typicalOpening?.value),
      secondary: (() => {
        const retention = ratioAsPercent(scope.typicalOpening?.retention);
        return retention === null ? null : `${retention} typical retention`;
      })(),
      help: "The median modeled opening outcome. Half of modeled openings finish above this value and half below. Taken from the pooled distribution across participating sets — not an average of each set's median.",
      primary: true,
    },
    {
      key: "chanceToRecover",
      label: "Chance to Recover Cost",
      value: ratioAsPercent(scope.chanceToBeatCost),
      help: "The modeled probability that an opening's card value reaches or exceeds its current purchase price.",
      primary: true,
    },
    {
      key: "averagePackPrice",
      label: "Average Pack Price",
      value: money(scope.meanPackCost),
      help: "The mean current market price of one loose booster pack across participating sets.",
    },
    {
      key: "modelBreakEven",
      label: "Average Model Break-Even",
      value: money(scope.expectedValue),
      help: "The purchase price where modeled Expected Value would equal cost. This is the modeled long-run Expected Value, expressed as a break-even price — not a second calculation.",
    },
  ];
}

/** Sortable era columns. Presentation order ONLY — never a canonical rank. */
export const ERA_SORT_OPTIONS = [
  { value: "modeledReturnOnSpend", label: "Modeled Return" },
  { value: "expectedEntertainmentCost", label: "Entertainment Cost" },
  { value: "entertainmentCostShare", label: "Entertainment Cost %" },
  { value: "typicalOpeningValue", label: "Typical Opening" },
  { value: "typicalRetention", label: "Typical Retention" },
  { value: "chanceToBeatCost", label: "Chance to Recover" },
  { value: "meanPackCost", label: "Avg Pack Price" },
  { value: "expectedValue", label: "Model Break-Even" },
  { value: "eraName", label: "Era" },
];

export const DEFAULT_ERA_SORT = { key: "modeledReturnOnSpend", direction: "desc" };

function eraSortValue(era, key) {
  if (key === "eraName") return String(era?.eraName || "");
  if (key === "typicalOpeningValue") return finite(era?.typicalOpening?.value);
  if (key === "typicalRetention") return finite(era?.typicalOpening?.retention);
  return finite(era?.[key]);
}

/**
 * Presentation sort. Nulls stay LAST in BOTH directions, matching the existing
 * rankings sort contract — a missing value is not a small value.
 */
export function sortEras(eras, key, direction) {
  const rows = Array.isArray(eras) ? [...eras] : [];
  const factor = direction === "asc" ? 1 : -1;
  return rows.sort((left, right) => {
    const leftValue = eraSortValue(left, key);
    const rightValue = eraSortValue(right, key);
    if (typeof leftValue === "string" || typeof rightValue === "string") {
      return String(leftValue).localeCompare(String(rightValue)) * factor;
    }
    if (leftValue === null && rightValue === null) {
      return String(left?.eraName || "").localeCompare(String(right?.eraName || ""));
    }
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    if (leftValue === rightValue) {
      return String(left?.eraName || "").localeCompare(String(right?.eraName || ""));
    }
    return (leftValue - rightValue) * factor;
  });
}

/** One era row projected for display. Every cell is a string or `null`. */
export function projectEraRow(era) {
  return {
    eraName: String(era?.eraName || ""),
    setCount: finite(era?.setCount),
    meanPackCost: money(era?.meanPackCost),
    expectedValue: money(era?.expectedValue),
    typicalOpening: money(era?.typicalOpening?.value),
    typicalRetention: ratioAsPercent(era?.typicalOpening?.retention),
    modeledReturn: ratioAsPercent(era?.modeledReturnOnSpend),
    entertainmentCost: money(era?.expectedEntertainmentCost),
    entertainmentCostShare: ratioAsPercent(era?.entertainmentCostShare),
    chanceToRecover: ratioAsPercent(era?.chanceToBeatCost),
  };
}
