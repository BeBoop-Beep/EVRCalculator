/**
 * Client-side column sorting for the Rankings table.
 *
 * WHAT THIS IS — AND WHAT IT IS DELIBERATELY NOT
 * ----------------------------------------------
 * This module re-ORDERS rows that are already in memory. It computes no score,
 * no rank, no tier and no cohort. Every value it reads is lifted verbatim from
 * the authoritative field the corresponding cell already displays, so a column's
 * sort key and its rendered value can never disagree:
 *
 *   Overall RIP          overallRipV8.relativeScore      (via exploreRankingConfig)
 *   Financial RIP        financialRipV3.relativeScore    (via exploreRankingConfig)
 *   Collector Appeal     canonical CA V3 relativeScore   (via canonicalRipV7)
 *   EV                   mean_value                      (simulation mean pack value)
 *   Average Loss         expected_loss_when_losing       (E[cost - value | value < cost])
 *   Market Pack Price    pack_cost
 *   Chance to Beat Cost  prob_profit
 *
 * There is no substitute formula anywhere in this file. A metric the backend did
 * not publish is `null` and stays `null` — it is never coerced to 0, never
 * back-filled from a neighbouring field and never borrowed from a retired model.
 *
 * SORTING IS NOT RANKING
 * ----------------------
 * The canonical leaderboard order (Overall RIP V7 rank, resolved server-side and
 * again by `sortTargetsByMode`) is the INPUT to this module, never its output.
 * Callers pass the canonically ordered array; the returned array is a
 * presentation permutation of exactly those same target objects. Nothing here
 * writes to a target, so `overallRipV8.rank` and every score on the row are the
 * same values after a sort as before it.
 *
 * NULLS ARE LAST IN BOTH DIRECTIONS
 * ---------------------------------
 * A missing value is not a small value and not a large one. Rows with no value
 * for the active column sink to the bottom whether the sort is ascending or
 * descending, so an unpriced set can never be presented as the cheapest and an
 * unscored set can never be presented as the worst.
 *
 * TIES ARE BROKEN BY THE CANONICAL ORDER
 * --------------------------------------
 * Equal values fall back to the row's index in the canonical input order, so a
 * tie resolves the same way on every render instead of depending on the engine's
 * sort implementation.
 */

import { getScoreForMode } from "../../constants/exploreRankingConfig.mjs";
import { readCanonicalBlock, readCanonicalOverallRipV10, resolveCanonicalRipV7 } from "./canonicalRipV7.mjs";
import { readOptionalRankingsChase } from "./rankingsPresentation.mjs";

export const SORT_DESC = "desc";
export const SORT_ASC = "asc";

/**
 * The initial leaderboard experience: Overall RIP, strongest first. Changing a
 * column changes only what this module returns — it does not change what the
 * default is.
 */
export const RANKINGS_DEFAULT_SORT = Object.freeze({
  column: "setRip",
  direction: SORT_DESC,
});

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * `prob_profit` is published as a probability, but a 0-100 percentage has shown
 * up in older rows. Normalising here keeps the sort key on one scale — and it is
 * the SAME normalisation the cell's formatter applies, so what is compared is
 * what is printed.
 */
export function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed > 1 ? parsed / 100 : parsed;
}

/**
 * AVERAGE LOSS WHEN LOSING — E[pack_cost - value | value < pack_cost], dollars.
 *
 * THE AUTHORITATIVE FIELD, NOT A DERIVATION
 * -----------------------------------------
 * `expected_loss_when_losing` is produced by the simulation
 * (`compute_downside_metrics` -> `expected_loss_given_loss`), persisted as a
 * REQUIRED column on `simulation_run_summary`, and already rendered on the set
 * page as "Average Loss When You Miss" (see RipStatisticsPageClient). Rankings
 * reads that same field so the two surfaces cannot state different losses for
 * one set. The camelCase alias is the same value under the name the set page's
 * own metric map already accepts — one field, two spellings, never two metrics.
 *
 * WHY THIS IS NOT `pack_cost - mean_value`
 * ----------------------------------------
 * That expression is the unconditional gap between price and Expected Value,
 * and it is silent about how large a loss actually is. A $10 pack that returns
 * $0 half the time and $20 the other half has an unconditional gap of $0 and an
 * average loss when losing of $10. The two answers are not close in production
 * either: on the current cohort the old expression understated the real figure
 * on every ranked set.
 *
 * There is deliberately NO fallback to the old expression. Reconstructing a
 * conditional statistic from an unconditional mean would put a number under this
 * label that the simulation never measured, so a target whose snapshot predates
 * the field's publication renders Unavailable and sorts last, exactly like any
 * other missing metric.
 *
 * The cell prints it with a leading minus sign; the value here is the positive
 * loss magnitude and is sorted like every other column — first click puts the
 * LARGEST average loss on top. No reversed semantics for this or any metric.
 */
export function readAverageLoss(target) {
  return toNumber(target?.expected_loss_when_losing ?? target?.expectedLossWhenLosing);
}

export function readTypicalOpening(target) {
  return toNumber(target?.median_value ?? target?.medianValue);
}

// The decision contract defines modelBreakEvenPrice as the unchanged expected
// modeled opening value. Prefer the explicit alias, then the existing mean.
export function readModelBreakEven(target) {
  return toNumber(target?.modelBreakEvenPrice ?? target?.model_break_even_price ?? target?.mean_value);
}

/**
 * Modeled Return: `EV / pack price x 100`.
 *
 * The same two published numbers the Model Break-Even and Market Price columns
 * already show, expressed as a ratio. Both must be present and the price must
 * be positive — a set missing either stays unavailable rather than sorting as
 * zero.
 */
export function readModeledReturnPercent(target) {
  const expectedValue = readModelBreakEven(target);
  const price = toNumber(target?.pack_cost);
  if (expectedValue === null || price === null || price <= 0) return null;
  return (expectedValue / price) * 100;
}

/**
 * Entertainment Cost: `pack price - EV`.
 *
 * Deliberately NOT the same metric as Average Loss When Losing, which this
 * table also exposes. Entertainment Cost is the UNCONDITIONAL gap between price
 * and long-run modeled value; Average Loss When Losing is the CONDITIONAL
 * average shortfall of the openings that fail to recover cost. Both are kept.
 *
 * A negative result is returned unchanged: a set whose modeled contents are
 * worth more than its pack price has a negative entertainment cost, and
 * clamping it would erase the most interesting rows.
 */
export function readEntertainmentCost(target) {
  const expectedValue = readModelBreakEven(target);
  const price = toNumber(target?.pack_cost);
  if (expectedValue === null || price === null || price <= 0) return null;
  return price - expectedValue;
}

/**
 * The canonical PUBLIC Collector Appeal for a target.
 *
 * Read through `canonicalRipV7`, the one reader for the current public RIP
 * model, so this table shows the same Collector Appeal number as the set page.
 * The retired flat `collector_appeal_score` / `collector_appeal_rank` columns on
 * the same row are CA7-era values ranked against a different population and must
 * not be read here.
 */
export function readCollectorAppealBlock(target) {
  return readCanonicalBlock(resolveCanonicalRipV7(target).collectorAppeal);
}

/**
 * Every sortable column, and the ONE authoritative field each one reads.
 * `label` is the header text so the header and the sort key cannot drift apart.
 */
export const RANKINGS_SORT_COLUMNS = {
  setRip: {
    id: "setRip",
    label: "Set RIP",
    read: (target) => readCanonicalOverallRipV10(target).publicScore,
  },
  overall: {
    id: "overall",
    label: "Overall RIP",
    read: (target) => getScoreForMode(target, "overall"),
  },
  financial: {
    id: "financial",
    label: "Financial RIP",
    read: (target) => getScoreForMode(target, "financial"),
  },
  collectorAppeal: {
    id: "collectorAppeal",
    label: "Collector Appeal",
    read: (target) => readCollectorAppealBlock(target).publicScore,
  },
  typicalOpening: {
    id: "typicalOpening",
    label: "Typical Opening",
    read: readTypicalOpening,
  },
  modelBreakEven: {
    id: "modelBreakEven",
    label: "Model Break-Even",
    read: readModelBreakEven,
  },
  modeledReturn: {
    id: "modeledReturn",
    label: "Modeled Return",
    read: readModeledReturnPercent,
  },
  entertainmentCost: {
    id: "entertainmentCost",
    label: "Entertainment Cost",
    read: readEntertainmentCost,
  },
  marketPrice: {
    id: "marketPrice",
    label: "Market Price",
    read: (target) => toNumber(target?.pack_cost),
  },
  chanceToBeatCost: {
    id: "chanceToBeatCost",
    label: "Chance to Beat Cost",
    read: (target) => normalizeProbability(target?.prob_profit),
  },
  topChase: {
    id: "topChase",
    label: "Top Chase Market Value",
    read: (target) => readOptionalRankingsChase(target)?.marketValue ?? null,
  },
};

export const RANKINGS_SORT_COLUMN_IDS = Object.keys(RANKINGS_SORT_COLUMNS);

export function isSortableColumn(columnId) {
  return Object.prototype.hasOwnProperty.call(RANKINGS_SORT_COLUMNS, columnId);
}

/**
 * Read the raw numeric sort value for a column. Exported so a test can assert
 * that ordering is driven by the number and not by the formatted string.
 */
export function readSortValue(target, columnId) {
  const column = RANKINGS_SORT_COLUMNS[columnId];
  if (!column) {
    return null;
  }
  const value = column.read(target);
  return toNumber(value);
}

/**
 * The state a header click produces.
 *
 * A column that is not currently selected starts DESCENDING — numerically
 * highest first. Clicking the already-selected column flips direction, and keeps
 * flipping. The rule is identical for all seven columns.
 */
export function nextSortState(current, columnId) {
  if (!isSortableColumn(columnId)) {
    return current;
  }
  if (current?.column !== columnId) {
    return { column: columnId, direction: SORT_DESC };
  }
  return {
    column: columnId,
    direction: current.direction === SORT_DESC ? SORT_ASC : SORT_DESC,
  };
}

/** The `aria-sort` token for a header, or undefined when it is not the active one. */
export function ariaSortFor(sort, columnId) {
  if (sort?.column !== columnId) {
    return undefined;
  }
  return sort.direction === SORT_ASC ? "ascending" : "descending";
}

/**
 * Order rows for presentation.
 *
 * @param canonicallyOrderedTargets rows already in canonical leaderboard order.
 * @returns a NEW array holding the SAME target objects, reordered.
 */
export function sortRankingsRows(canonicallyOrderedTargets, sort = RANKINGS_DEFAULT_SORT) {
  const rows = Array.isArray(canonicallyOrderedTargets) ? canonicallyOrderedTargets : [];
  const column = RANKINGS_SORT_COLUMNS[sort?.column];

  // The default view is the canonical order itself, returned untouched. Overall
  // RIP descending and the canonical rank ascending are the same ordering, and
  // deferring to the canonical array rather than re-deriving it means the
  // initial leaderboard cannot drift from the server-rendered one.
  if (!column || (sort.column === RANKINGS_DEFAULT_SORT.column && sort.direction === SORT_DESC)) {
    return rows.slice();
  }

  const descending = sort.direction !== SORT_ASC;
  const decorated = rows.map((target, canonicalIndex) => ({
    target,
    canonicalIndex,
    value: toNumber(column.read(target)),
  }));

  decorated.sort((left, right) => {
    if (left.value === null || right.value === null) {
      if (left.value === right.value) {
        return left.canonicalIndex - right.canonicalIndex;
      }
      // Unavailable sinks in BOTH directions — never the best, never the worst.
      return left.value === null ? 1 : -1;
    }
    if (left.value !== right.value) {
      return descending ? right.value - left.value : left.value - right.value;
    }
    return left.canonicalIndex - right.canonicalIndex;
  });

  return decorated.map((entry) => entry.target);
}
