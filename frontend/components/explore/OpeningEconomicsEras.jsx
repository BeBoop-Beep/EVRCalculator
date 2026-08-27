"use client";

import React, { useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import styles from "./explore.module.css";
import {
  DEFAULT_ERA_SORT,
  ERA_SORT_OPTIONS,
  UNAVAILABLE_LABEL,
  isAvailable,
  projectEraRow,
  sortEras,
} from "./openingEconomicsSelector.mjs";

/**
 * The Eras lens: the same loose-pack economics, partitioned by era.
 *
 * Sorting here is PRESENTATION ONLY. No era carries a rank, tier or score, and
 * none is persisted — the ordering exists so a reader can compare, not so the
 * product can declare a winner.
 */

const COLUMNS = [
  { key: "eraName", label: "Era", sort: "eraName", align: "left" },
  { key: "setCount", label: "Sets", sort: null, align: "right", priority: 2 },
  { key: "modeledReturn", label: "Modeled Return", sort: "modeledReturnOnSpend", align: "right", priority: 1 },
  { key: "typicalOpening", label: "Typical Opening", sort: "typicalOpeningValue", align: "right", priority: 1 },
  { key: "typicalRetention", label: "Typical Retention", sort: "typicalRetention", align: "right", priority: 1 },
  { key: "entertainmentCost", label: "Ent. Cost / Pack", sort: "expectedEntertainmentCost", align: "right", priority: 1 },
  { key: "entertainmentCostShare", label: "Ent. Cost %", sort: "entertainmentCostShare", align: "right", priority: 2 },
  { key: "chanceToRecover", label: "Chance to Recover", sort: "chanceToBeatCost", align: "right", priority: 1 },
  { key: "meanPackCost", label: "Avg Pack Price", sort: "meanPackCost", align: "right", priority: 2 },
  { key: "expectedValue", label: "Model Break-Even", sort: "expectedValue", align: "right", priority: 2 },
];

function Cell({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-[var(--text-secondary)] opacity-70">—</span>;
  }
  return value;
}

export default function OpeningEconomicsEras({ economics, onSelectSets = null }) {
  const [sort, setSort] = useState(DEFAULT_ERA_SORT);

  const rows = useMemo(() => {
    const eras = Array.isArray(economics?.eras) ? economics.eras : [];
    return sortEras(eras, sort.key, sort.direction).map((era) => ({
      raw: era,
      cells: projectEraRow(era),
    }));
  }, [economics, sort]);

  if (!isAvailable(economics) || rows.length === 0) {
    return (
      <section className={`${styles.surface} rounded-xl p-6`} data-opening-economics-eras-unavailable>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Opening Economics by Era</h2>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          Era economics are {UNAVAILABLE_LABEL.toLowerCase()} right now. The other ranking views are unaffected.
        </p>
      </section>
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

  return (
    <section data-opening-economics-eras>
      <header className="mb-3">
        <h2 className="text-lg font-semibold tracking-tight text-[var(--text-primary)] sm:text-xl">
          Opening Economics by Era
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Compare how the economics of opening one loose booster pack differ across Pokémon eras.
        </p>
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
          Each era pools every modeled opening from its own sets, with each set weighted equally within the era.{" "}
          <InfoPopover text="Typical Opening and Typical Retention are pooled medians taken from the era's own combined outcome population — not an average of its sets' individual medians. Sorting orders the table for reading only; eras are not scored, ranked or tiered." />
        </p>
      </header>

      {/* Desktop: full table. Wide secondary columns drop out below `desk` and
          return in the mobile card list below, rather than forcing a table
          nobody can read. */}
      <div className={`${styles.scrollShell} hidden desk:block`}>
        <table className={`${styles.table} w-full text-sm`} data-era-table>
          <thead>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort.key === column.sort;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    className={column.align === "left" ? "text-left" : "text-right"}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  >
                    {column.sort ? (
                      <button
                        type="button"
                        className={styles.sortButton}
                        onClick={() => toggleSort(column.sort)}
                        data-era-sort={column.sort}
                      >
                        {column.label}
                        {active ? <span aria-hidden="true">{sort.direction === "asc" ? " ↑" : " ↓"}</span> : null}
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
                <th scope="row" className="text-left font-medium text-[var(--text-primary)]">
                  {onSelectSets ? (
                    <button
                      type="button"
                      onClick={() => onSelectSets(raw)}
                      className="text-left underline-offset-2 hover:underline"
                      data-era-drilldown
                    >
                      {cells.eraName}
                    </button>
                  ) : (
                    cells.eraName
                  )}
                </th>
                {COLUMNS.slice(1).map((column) => (
                  <td key={column.key} className={`${styles.numeric} text-right`}>
                    <Cell value={cells[column.key]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: one card per era, leading with the primary metrics. */}
      <ul className="space-y-2.5 desk:hidden" data-era-cards>
        {rows.map(({ raw, cells }) => (
          <li key={cells.eraName} className={`${styles.surface} rounded-xl p-3.5`}>
            <div className="flex items-baseline justify-between gap-2">
              {onSelectSets ? (
                <button
                  type="button"
                  onClick={() => onSelectSets(raw)}
                  className="text-sm font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
                >
                  {cells.eraName}
                </button>
              ) : (
                <span className="text-sm font-semibold text-[var(--text-primary)]">{cells.eraName}</span>
              )}
              <span className="text-xs text-[var(--text-secondary)]">
                <Cell value={cells.setCount} /> sets
              </span>
            </div>
            <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2">
              {[
                ["Modeled Return", cells.modeledReturn],
                ["Typical Retention", cells.typicalRetention],
                ["Ent. Cost / Pack", cells.entertainmentCost],
                ["Chance to Recover", cells.chanceToRecover],
                ["Typical Opening", cells.typicalOpening],
                ["Avg Pack Price", cells.meanPackCost],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-[0.68rem] uppercase tracking-wide text-[var(--text-secondary)]">{label}</dt>
                  <dd className="mt-0.5 text-sm font-medium tabular-nums text-[var(--text-primary)]">
                    <Cell value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      <p className="mt-4 text-xs leading-relaxed text-[var(--text-secondary)]">
        Modeled values use gross tracked card-market value. Selling fees, shipping, liquidity, grading costs and spreads
        are not deducted.
      </p>
    </section>
  );
}
