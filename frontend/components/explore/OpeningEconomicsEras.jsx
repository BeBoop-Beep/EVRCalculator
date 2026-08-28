"use client";

import React, { useMemo, useState } from "react";
import AnalyticsTableShell from "./AnalyticsTableShell";
import styles from "./explore.module.css";
import { OpeningEconomicsEmpty, OpeningEconomicsSkeleton } from "./OpeningEconomicsOverall";
import {
  DEFAULT_ERA_SORT,
  isAvailable,
  projectEraRow,
  sortEras,
} from "./openingEconomicsSelector.mjs";

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
  { key: "modeledReturn", label: "Modeled Return", sort: "modeledReturnOnSpend", emphasis: "primary" },
  { key: "typicalOpening", label: "Typical Opening / Pack", sort: "typicalOpeningValue" },
  { key: "typicalRetention", label: "Typical Retention", sort: "typicalRetention" },
  { key: "entertainmentCost", label: "Entertainment Cost / Pack", sort: "expectedEntertainmentCost", secondary: "entertainmentCostShare" },
  { key: "chanceToRecover", label: "Chance to Recover", sort: "chanceToBeatCost" },
  { key: "meanPackCost", label: "Avg Cost / Pack", sort: "meanPackCost", emphasis: "quiet" },
  { key: "expectedValue", label: "Break-Even / Pack", sort: "expectedValue", emphasis: "quiet" },
];

function Dash() {
  return <span className="text-[var(--text-secondary)] opacity-60">—</span>;
}

function valueClass(emphasis) {
  if (emphasis === "primary") return "text-sm font-semibold text-[var(--text-primary)]";
  if (emphasis === "quiet") return "text-xs text-[var(--text-secondary)]";
  return "text-xs text-[var(--text-primary)]";
}

export default function OpeningEconomicsEras({ economics, onSelectEra = null }) {
  const [sort, setSort] = useState(DEFAULT_ERA_SORT);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const eras = (Array.isArray(economics?.eras) ? economics.eras : []).filter((era) => !needle || String(era?.eraName || "").toLowerCase().includes(needle));
    return sortEras(eras, sort.key, sort.direction).map((era) => ({ raw: era, cells: projectEraRow(era) }));
  }, [economics, query, sort]);

  // Projected through the SAME reader as an era row, so the baseline can never
  // drift into a differently-formatted or differently-sourced number.
  const baseline = projectEraRow({ ...(economics?.global || {}), eraName: "All modeled sets" });

  if (economics?.status === "loading") return <OpeningEconomicsSkeleton />;
  if (!isAvailable(economics) || rows.length === 0) {
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
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "desc" ? "asc" : "desc" }
        : { key, direction: key === "eraName" ? "asc" : "desc" },
    );
  };

  const drilldownLabel = (eraName) => `View the ${eraName} sets`;

  return (
    <AnalyticsTableShell title="Pack Economics by Era" info="All eligible modeled sealed products are normalized per pack. Sets are equally weighted within each Era. Typical Opening and Typical Retention are pooled medians from each era's own combined outcomes; sorting is presentation only." query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search eras..." searchLabel="Search eras" context="Select an era for the full Pack Economics breakdown." shown={rows.length} marketDate={economics.marketDate}>
    <section data-opening-economics-eras>

      {/* Desktop: compact, dense table. */}
      <div className="hidden overflow-x-auto desk:block">
        <table className={styles.table} data-era-table>
          <caption className="sr-only">
            Opening economics by era. Sortable; sorting changes display order only and does not rank eras.
          </caption>
          <thead className={`${styles.head} ${styles.analyticsTableHead}`}>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort.key === column.sort;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    className={`text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)] ${
                      column.align === "left" ? "text-left" : "text-right"
                    }`}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  >
                    {column.sort ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.sort)}
                        data-era-sort={column.sort}
                        className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-[var(--text-primary)]"
                      >
                        {column.label}
                        <span aria-hidden="true" className={active ? "opacity-100" : "opacity-0"}>
                          {sort.direction === "asc" ? "↑" : "↓"}
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
              <tr key={cells.eraName} className={styles.row} data-era-row={cells.eraName}>
                <th scope="row" className="text-left">
                  {onSelectEra ? (
                    <button
                      type="button"
                      onClick={() => onSelectEra(raw)}
                      data-era-drilldown
                      aria-label={drilldownLabel(cells.eraName)}
                      className="text-sm font-medium text-[var(--text-primary)] underline-offset-2 hover:underline"
                    >
                      {cells.eraName}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-[var(--text-primary)]">{cells.eraName}</span>
                  )}
                </th>
                {COLUMNS.slice(1).map((column) => (
                  <td key={column.key} className="text-right tabular-nums">
                    <span className={valueClass(column.emphasis)}>{cells[column.key] ?? <Dash />}</span>
                    {column.secondary && cells[column.secondary] ? (
                      <span className="ml-1 text-[0.65rem] text-[var(--text-secondary)]">
                        {cells[column.secondary]}
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {/* The all-sets baseline, so an era's numbers are read against the
              whole modeled market rather than only against each other. It is
              the SAME published global scope the Overall lens renders — not a
              total recomputed from the era rows above. */}
          <tfoot>
            <tr data-era-baseline-row>
              <th scope="row" className="border-t border-[var(--ex-line-strong)] text-left text-xs font-medium text-[var(--text-secondary)]">
                All modeled sets
              </th>
              {COLUMNS.slice(1).map((column) => (
                <td
                  key={column.key}
                  className="border-t border-[var(--ex-line-strong)] text-right text-xs tabular-nums text-[var(--text-secondary)]"
                >
                  {baseline[column.key] ?? <Dash />}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Mobile: one card per era, primary metrics first, secondary beneath. */}
      <ul className="space-y-2.5 p-3 desk:hidden" data-era-cards>
        {rows.map(({ raw, cells }) => (
          <li key={cells.eraName} className={`${styles.surface} rounded-xl p-3.5`}>
            <div className="flex items-baseline justify-between gap-2">
              {onSelectEra ? (
                <button
                  type="button"
                  onClick={() => onSelectEra(raw)}
                  aria-label={drilldownLabel(cells.eraName)}
                  className="text-sm font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
                >
                  {cells.eraName}
                </button>
              ) : (
                <span className="text-sm font-semibold text-[var(--text-primary)]">{cells.eraName}</span>
              )}
              <span className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
                {cells.setCount ?? <Dash />} sets
              </span>
            </div>

            <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2">
              {[
                ["Modeled Return", cells.modeledReturn, true],
                ["Typical Retention", cells.typicalRetention, false],
                ["Entertainment Cost", cells.entertainmentCost, false],
                ["Chance to Recover", cells.chanceToRecover, false],
              ].map(([label, value, strong]) => (
                <div key={label}>
                  <dt className="text-[0.65rem] uppercase tracking-wide text-[var(--text-secondary)]">{label}</dt>
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

            <dl className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--ex-line)] pt-2 text-[0.68rem] text-[var(--text-secondary)]">
              {[
                ["Typical Opening", cells.typicalOpening],
                ["Avg Pack Price", cells.meanPackCost],
                ["Break-Even", cells.expectedValue],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-1.5">
                  <dt>{label}</dt>
                  <dd className="tabular-nums text-[var(--text-primary)]">{value ?? <Dash />}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      <div className={`${styles.surfaceQuiet} mt-2.5 rounded-xl p-3 desk:hidden`} data-era-baseline-card>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs font-medium text-[var(--text-secondary)]">All modeled sets</span>
          <span className="text-[0.68rem] tabular-nums text-[var(--text-secondary)]">
            {baseline.setCount ?? <Dash />} sets
          </span>
        </div>
        <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.68rem] text-[var(--text-secondary)]">
          {[
            ["Modeled Return", baseline.modeledReturn],
            ["Typical Retention", baseline.typicalRetention],
            ["Entertainment Cost", baseline.entertainmentCost],
          ].map(([label, value]) => (
            <div key={label} className="flex gap-1.5">
              <dt>{label}</dt>
              <dd className="tabular-nums text-[var(--text-primary)]">{value ?? <Dash />}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="border-t border-[var(--border-subtle)] px-3 py-3 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">
        Card values reflect modeled gross market value. Selling fees, shipping, liquidity, grading costs, and other
        transaction costs are not deducted.
      </p>
    </section>
    </AnalyticsTableShell>
  );
}
