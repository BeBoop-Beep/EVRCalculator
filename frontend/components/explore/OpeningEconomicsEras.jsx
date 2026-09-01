"use client";

import React, { useMemo, useState } from "react";
import AnalyticsTableShell from "./AnalyticsTableShell";
import { PremiumMetricLock } from "./RankedProductTablePrimitives.jsx";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import styles from "./explore.module.css";
import {
  OpeningEconomicsEmpty,
  OpeningEconomicsSkeleton,
} from "./OpeningEconomicsOverall";
import {
  DEFAULT_ERA_SORT,
  isAvailable,
  projectEraRow,
  sortEras,
} from "./openingEconomicsSelector.mjs";

const PLUS_COMPACT_LOCK = planPresentation(INDEX_PLAN_PLUS).compactClassName;

/**
 * The Eras lens: all eligible sealed-product economics, partitioned by era.
 *
 * Sorting is PRESENTATION ONLY. No era carries a rank, tier or score, none is
 * persisted, and no row is ever marked as the winner — the metrics are left to
 * explain the difference themselves.
 */

/** `emphasis` drives type weight, so the table has hierarchy without color. */
const COLUMNS = [
  { key: "eraName", label: "Era", sort: "eraName", align: "left" },
  { key: "setCount", label: "Sets", sort: null },
  { key: "productSkuCount", label: "Products", sort: null },
  {
    key: "modeledReturn",
    label: "Modeled Return",
    sort: "modeledReturnOnSpend",
    emphasis: "primary",
  },
  {
    key: "typicalOpening",
    label: "Typical Opening / Pack",
    sort: "typicalOpeningValue",
  },
  {
    key: "typicalRetention",
    label: "Typical Retention",
    sort: "typicalRetention",
  },
  {
    key: "entertainmentCost",
    label: "Entertainment Cost / Pack",
    sort: "expectedEntertainmentCost",
    secondary: "entertainmentCostShare",
  },
  {
    key: "chanceToRecover",
    label: "Chance to Recover",
    sort: "chanceToBeatCost",
  },
  {
    key: "meanPackCost",
    label: "Avg Cost / Pack",
    sort: "meanPackCost",
    emphasis: "quiet",
  },
  {
    key: "expectedValue",
    label: "Break-Even / Pack",
    sort: "expectedValue",
    emphasis: "quiet",
  },
];
const PUBLIC_ERA_COLUMN_KEYS = new Set([
  "eraName",
  "setCount",
  "productSkuCount",
  "meanPackCost",
]);

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function valueClass(emphasis) {
  if (emphasis === "primary")
    return "text-sm font-semibold text-[var(--text-primary)]";
  if (emphasis === "quiet") return "text-xs text-[var(--text-secondary)]";
  return "text-xs text-[var(--text-primary)]";
}

function EraEconomicsCell({
  column,
  cells,
  raw = null,
  onSelectEra = null,
  baseline = false,
  canViewRankingsIntelligence,
}) {
  const identity = column.key === "eraName";
  const Cell = identity ? "th" : "td";
  const locked =
    !canViewRankingsIntelligence && !PUBLIC_ERA_COLUMN_KEYS.has(column.key);
  const sharedClass = `${styles.eraEconomicsCell} ${identity ? "text-left" : "text-right tabular-nums"} ${baseline ? "text-[var(--text-secondary)]" : ""}`;
  let content = locked ? (
    <PremiumMetricLock />
  ) : (
    <>
      <span className={valueClass(column.emphasis)}>
        {cells[column.key] ?? <Dash />}
      </span>
      {column.secondary && cells[column.secondary] ? (
        <span className="ml-1 text-[0.65rem] text-[var(--text-secondary)]">
          {cells[column.secondary]}
        </span>
      ) : null}
    </>
  );
  if (identity)
    content =
      !baseline && onSelectEra ? (
        <button
          type="button"
          onClick={() => onSelectEra(raw)}
          data-era-drilldown
          aria-label={`View the ${cells.eraName} sets`}
          className="text-sm font-medium text-[var(--text-primary)] underline-offset-2 hover:underline"
        >
          {cells.eraName}
        </button>
      ) : (
        <span
          className={`text-sm ${baseline ? "font-semibold text-[var(--text-secondary)]" : "font-medium text-[var(--text-primary)]"}`}
        >
          {cells.eraName}
        </span>
      );
  return (
    <Cell
      key={column.key}
      scope={identity ? "row" : undefined}
      className={sharedClass}
      data-era-economics-cell={column.key}
    >
      {content}
    </Cell>
  );
}

export default function OpeningEconomicsEras({
  economics,
  onSelectEra = null,
  canViewRankingsIntelligence = false,
  onUnlockProductRip = null,
}) {
  const [sort, setSort] = useState(() =>
    canViewRankingsIntelligence
      ? DEFAULT_ERA_SORT
      : { key: "eraName", direction: "asc" },
  );
  const [query, setQuery] = useState("");
  const selectedSortColumn = COLUMNS.find((column) => column.sort === sort.key);
  const effectiveSort =
    canViewRankingsIntelligence ||
    PUBLIC_ERA_COLUMN_KEYS.has(selectedSortColumn?.key)
      ? sort
      : { key: "eraName", direction: "asc" };

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const eras = (Array.isArray(economics?.eras) ? economics.eras : []).filter(
      (era) =>
        !needle ||
        String(era?.eraName || "")
          .toLowerCase()
          .includes(needle),
    );
    return sortEras(eras, effectiveSort.key, effectiveSort.direction).map(
      (era) => ({ raw: era, cells: projectEraRow(era) }),
    );
  }, [economics, effectiveSort.direction, effectiveSort.key, query]);

  // Projected through the SAME reader as an era row, so the baseline can never
  // drift into a differently-formatted or differently-sourced number.
  const baseline = projectEraRow({
    ...(economics?.global || {}),
    eraName: "All modeled sets",
  });

  if (economics?.status === "loading") return <OpeningEconomicsSkeleton />;
  if (
    !isAvailable(economics) ||
    !Array.isArray(economics?.eras) ||
    economics.eras.length === 0
  ) {
    return (
      <OpeningEconomicsEmpty
        economics={economics}
        title="Opening Economics by Era"
        subject="Era economics"
      />
    );
  }

  const toggleSort = (key) => {
    if (!key) return;
    const column = COLUMNS.find((candidate) => candidate.sort === key);
    if (
      !canViewRankingsIntelligence &&
      column &&
      !PUBLIC_ERA_COLUMN_KEYS.has(column.key)
    ) {
      onUnlockProductRip?.();
      return;
    }
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "desc" ? "asc" : "desc" }
        : { key, direction: key === "eraName" ? "asc" : "desc" },
    );
  };

  return (
    <AnalyticsTableShell
      title="Pack Economics by Era"
      info="Every eligible modeled sealed product is normalized to a per-pack equivalent. Sets receive equal weight within each Era. Typical values come from each Era's published weighted empirical product-opening distribution."
      query={query}
      onQueryChange={(event) => setQuery(event.target.value)}
      searchPlaceholder="Search eras..."
      searchLabel="Search eras"
      context="Select an era for the full Pack Economics breakdown."
      shown={rows.length}
      marketDate={economics.marketDate}
    >
      <section
        data-opening-economics-eras
        data-pack-economics-entitled={
          canViewRankingsIntelligence ? "true" : "false"
        }
      >
        {/* Desktop: compact, dense table. */}
        <div className="hidden overflow-x-auto desk:block">
          <table className={styles.table} data-era-table>
            <caption className="sr-only">
              Opening economics by era. Sortable; sorting changes display order
              only and does not rank eras.
            </caption>
            <colgroup data-era-economics-colgroup>
              {COLUMNS.map((column) => (
                <col
                  key={column.key}
                  style={{
                    width:
                      column.key === "eraName"
                        ? "17%"
                        : column.key === "setCount" ||
                            column.key === "productSkuCount"
                          ? "6%"
                          : "10.125%",
                  }}
                />
              ))}
            </colgroup>
            <thead className={`${styles.head} ${styles.analyticsTableHead}`}>
              <tr>
                {COLUMNS.map((column) => {
                  const active = effectiveSort.key === column.sort;
                  return (
                    <th
                      key={column.key}
                      scope="col"
                      className={`text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)] ${
                        column.align === "left" ? "text-left" : "text-right"
                      }`}
                      aria-sort={
                        active
                          ? effectiveSort.direction === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      {column.sort ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.sort)}
                          data-era-sort={column.sort}
                          className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-[var(--text-primary)]"
                        >
                          {column.label}
                          <span
                            aria-hidden="true"
                            className={active ? "opacity-100" : "opacity-0"}
                          >
                            {effectiveSort.direction === "asc" ? "↑" : "↓"}
                          </span>
                        </button>
                      ) : (
                        column.label
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ raw, cells }) => (
                <tr
                  key={cells.eraName}
                  className={styles.row}
                  data-era-row={cells.eraName}
                >
                  {COLUMNS.map((column) => (
                    <EraEconomicsCell
                      key={column.key}
                      column={column}
                      cells={cells}
                      raw={raw}
                      onSelectEra={onSelectEra}
                      canViewRankingsIntelligence={canViewRankingsIntelligence}
                    />
                  ))}
                </tr>
              ))}
              {/* The all-sets baseline is a peer data row, separated only by a
                stronger top rule. It uses the same cells and colgroup as every
                Era above, so its geometry cannot drift. */}
              <tr
                className={`${styles.row} ${styles.eraGlobalBaselineRow}`}
                data-era-baseline-row
              >
                {COLUMNS.map((column) => (
                  <EraEconomicsCell
                    key={column.key}
                    column={column}
                    cells={baseline}
                    baseline
                    canViewRankingsIntelligence={canViewRankingsIntelligence}
                  />
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Mobile: one card per era, primary metrics first, secondary beneath. */}
        <ul className="space-y-2.5 p-3 desk:hidden" data-era-cards>
          {rows.map(({ raw, cells }) => (
            <li
              key={cells.eraName}
              className={`${styles.surface} rounded-xl p-3.5`}
            >
              <div className="flex items-baseline justify-between gap-2">
                {onSelectEra ? (
                  <button
                    type="button"
                    onClick={() => onSelectEra(raw)}
                    aria-label={`View the ${cells.eraName} sets`}
                    className="text-sm font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
                  >
                    {cells.eraName}
                  </button>
                ) : (
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {cells.eraName}
                  </span>
                )}
                <span className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
                  {cells.setCount ?? <Dash />} sets
                </span>
              </div>

              {canViewRankingsIntelligence ? (
                <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2">
                  {[
                    ["Modeled Return", cells.modeledReturn, true],
                    ["Typical Retention", cells.typicalRetention, false],
                    ["Entertainment Cost", cells.entertainmentCost, false],
                    ["Chance to Recover", cells.chanceToRecover, false],
                  ].map(([label, value, strong]) => (
                    <div key={label}>
                      <dt className="text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">
                        {label}
                      </dt>
                      <dd
                        className={`mt-0.5 tabular-nums ${
                          strong
                            ? "text-base font-semibold text-[var(--text-primary)]"
                            : "text-sm text-[var(--text-primary)]"
                        }`}
                      >
                        {value ?? <Dash />}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : null}

              {canViewRankingsIntelligence ? (
                <dl className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--ex-line)] pt-2 text-[0.68rem] text-[var(--text-secondary)]">
                  {[
                    ["Typical Opening", cells.typicalOpening],
                    ["Avg Pack Price", cells.meanPackCost],
                    ["Break-Even", cells.expectedValue],
                  ].map(([label, value]) => (
                    <div key={label} className="flex gap-1.5">
                      <dt>{label}</dt>
                      <dd className="tabular-nums text-[var(--text-primary)]">
                        {value ?? <Dash />}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <div className="mt-2.5 border-t border-[var(--ex-line)] pt-2 text-xs">
                  <p className="tabular-nums text-[var(--text-primary)]">
                    {cells.productSkuCount ?? <Dash />} products ·{" "}
                    {cells.meanPackCost ?? <Dash />} avg cost / pack
                  </p>
                  <button
                    type="button"
                    onClick={() => onUnlockProductRip?.()}
                    className={`mt-2 rounded-md border px-2 py-1 text-left focus-visible:outline-none focus-visible:ring-2 ${PLUS_COMPACT_LOCK}`}
                  >
                    Index Plus required for full Pack Economics
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>

        <div
          className={`${styles.surfaceQuiet} mt-2.5 rounded-xl p-3 desk:hidden`}
          data-era-baseline-card
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs font-medium text-[var(--text-secondary)]">
              All modeled sets
            </span>
            <span className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
              {baseline.setCount ?? <Dash />} sets
            </span>
          </div>
          {canViewRankingsIntelligence ? (
            <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.68rem] text-[var(--text-secondary)]">
              {[
                ["Modeled Return", baseline.modeledReturn],
                ["Typical Retention", baseline.typicalRetention],
                ["Entertainment Cost", baseline.entertainmentCost],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-1.5">
                  <dt>{label}</dt>
                  <dd className="tabular-nums text-[var(--text-primary)]">
                    {value ?? <Dash />}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
              {baseline.productSkuCount ?? <Dash />} products ·{" "}
              {baseline.meanPackCost ?? <Dash />} avg cost / pack
            </p>
          )}
        </div>

        <p className="border-t border-[var(--border-subtle)] px-3 py-3 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">
          Card values reflect modeled gross market value. Selling fees,
          shipping, liquidity, grading costs, and other transaction costs are
          not deducted.
        </p>
      </section>
    </AnalyticsTableShell>
  );
}
