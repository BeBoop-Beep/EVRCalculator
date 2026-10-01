"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import PlanLock from "@/components/membership/PlanLock";
import { INDEX_PLAN_PLUS } from "@/lib/access/indexPlanAccess.mjs";
import { RankingsBenchmarkComponentScore, RankingsRipScoreBadge } from "./RankingsScorePrimitives";
import {
  ariaSort,
  DEFAULT_SORT,
  displayedRank,
  effectiveSort,
  filterScoreRows,
  nextSort,
  REFERENCE_SCORE,
  SCORE_COLUMNS,
  sortableKeys,
  sortScoreRows,
} from "./unifiedScoreTableModel.mjs";
import styles from "./explore.module.css";

const COMPONENT_COLUMNS = SCORE_COLUMNS.filter((column) => column.protectedColumn);

function LockedCell({ label }) {
  return <span data-rankings-locked-cell className="inline-flex min-w-[2.75rem] items-center justify-center rounded-md border border-dashed border-[var(--border-subtle)] px-2 py-0.5 text-xs text-[var(--text-secondary)]"><span aria-hidden="true">🔒</span><span className="sr-only">{label} is included with Index Plus</span></span>;
}

function PendingCell({ label }) {
  return <span data-rankings-pending-cell aria-busy="true" className="inline-block h-6 w-11 animate-pulse rounded-md bg-white/10"><span className="sr-only">{label} loading</span></span>;
}

function ScoreCell({ column, row, entitled, paidStatus }) {
  if (column.key === "overall") return <RankingsRipScoreBadge metric={row.overall} label={`${column.label}`} compact />;
  if (!entitled) return <LockedCell label={column.label} />;
  if (paidStatus === "loading" && !row[column.key]) return <PendingCell label={column.label} />;
  return <RankingsBenchmarkComponentScore metric={row[column.key]} label={column.label} />;
}

function RankCell({ row, sortKey }) {
  const rank = displayedRank(row, sortKey);
  if (!rank) return <>—</>;
  return <>#{rank.rank}{rank.cohortSize ? <span className="sr-only"> of {rank.cohortSize}</span> : null}</>;
}

function ReferenceCells({ entitled, showModeledSets }) {
  const plain = <strong className="tabular-nums text-[var(--text-primary)]">{REFERENCE_SCORE.toFixed(1)}</strong>;
  return <>
    <td className={styles.numeric}><span className="sr-only">No rank</span></td>
    <td><span className="inline-flex items-center gap-2 font-medium"><span aria-hidden="true">◉</span>Pokémon Overall Average</span><span className="sr-only"> Benchmark reference; not ranked</span></td>
    <td className={styles.numeric}>{plain}</td>
    {COMPONENT_COLUMNS.map((column) => <td className={styles.numeric} key={column.key}>{entitled ? plain : <LockedCell label={column.label} />}</td>)}
    {showModeledSets ? <td /> : null}
  </>;
}

function SortHeader({ column, sort, entitled, onSort }) {
  const allowed = sortableKeys(entitled).includes(column.key);
  const active = sort.key === column.key;
  return <th scope="col" aria-sort={ariaSort(sort, column.key)} className={styles.numeric}>
    <button type="button" data-sort-key={column.key} disabled={!allowed} aria-disabled={!allowed} title={allowed ? undefined : "Included with Index Plus"} onClick={() => onSort(column.key)} className="inline-flex items-center gap-1 whitespace-nowrap font-[inherit] uppercase tracking-[inherit] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(196,181,253,.78)] enabled:hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-60">
      {!allowed ? <span aria-hidden="true">🔒</span> : null}{column.label}{active ? <span aria-hidden="true">{sort.direction === "asc" ? "▲" : "▼"}</span> : null}
    </button>
  </th>;
}

/**
 * One sortable benchmark score table per entity type.  Rank, tier and cohort
 * are the canonical backend values of the metric currently sorted by; search
 * and sorting are client-local and never recompute them.
 */
export default function BenchmarkEntityScoreTable({
  entityLabel = "Set",
  rows = [],
  query = "",
  eraFilter = null,
  entitled = false,
  paidStatus = "idle",
  showModeledSets = false,
  renderIdentity,
  getHref = null,
  emptyMessage = "No rankings match the current filters.",
}) {
  const [requested, setRequested] = useState(DEFAULT_SORT);
  const sort = effectiveSort(requested, entitled);
  const visible = useMemo(() => sortScoreRows(filterScoreRows(rows, { query, eraFilter }), sort), [rows, query, eraFilter, sort]);
  const onSort = (key) => setRequested((current) => nextSort(effectiveSort(current, entitled), key, entitled));
  if (!visible.length) return <p className="p-5 text-sm text-[var(--text-secondary)]">{emptyMessage}</p>;
  const identity = (row, index, mobile) => {
    const content = renderIdentity(row, index, mobile);
    const href = getHref?.(row);
    return href ? <Link href={href} className={styles.rowLink}>{content}</Link> : content;
  };
  return <div data-rankings-score-table data-rankings-unified-score-table={entityLabel.toLowerCase()} data-active-sort-key={sort.key} data-active-sort-direction={sort.direction}>
    {!entitled ? <div className="px-3 pb-2 pt-3 sm:px-5"><PlanLock compact requiredPlan={INDEX_PLAN_PLUS} source={`rankings-${entityLabel.toLowerCase()}-components`} /></div> : null}
    <div role="group" aria-label={`Sort ${entityLabel} scores`} className="flex gap-2 overflow-x-auto px-3 pb-2 md:hidden" data-rankings-mobile-sort>
      {SCORE_COLUMNS.map((column) => {
        const allowed = sortableKeys(entitled).includes(column.key);
        return <button key={column.key} type="button" disabled={!allowed} aria-pressed={sort.key === column.key} onClick={() => onSort(column.key)} className={`${styles.productFamilyTab} shrink-0 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 ${sort.key === column.key ? styles.productFamilyTabActive : ""}`}>{column.label}{sort.key === column.key ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}</button>;
      })}
    </div>
    <div className="hidden overflow-x-auto md:block">
      <table className={styles.table}>
        <caption className="sr-only">{entityLabel} score rankings with Pokémon Overall Average reference. Rank shows the canonical rank of the metric the table is sorted by.</caption>
        <thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr>
          <th scope="col" className={styles.numeric}>Rank</th>
          <th scope="col">{entityLabel}</th>
          {SCORE_COLUMNS.map((column) => <SortHeader key={column.key} column={column} sort={sort} entitled={entitled} onSort={onSort} />)}
          {showModeledSets ? <th scope="col" className={styles.numeric}>Modeled Sets</th> : null}
        </tr></thead>
        <tbody>
          <tr data-rankings-reference-row className="bg-white/[.025] text-[var(--text-secondary)]"><ReferenceCells entitled={entitled} showModeledSets={showModeledSets} /></tr>
          {visible.map((row, index) => <tr key={row.entityId} className={styles.row} data-entity-id={row.entityId}>
            <td className={`${styles.numeric} text-sm font-bold`}><RankCell row={row} sortKey={sort.key} /></td>
            <td>{identity(row, index, false)}</td>
            {SCORE_COLUMNS.map((column) => <td className={styles.numeric} key={column.key}><ScoreCell column={column} row={row} entitled={entitled} paidStatus={paidStatus} /></td>)}
            {showModeledSets ? <td className={`${styles.numeric} tabular-nums`}>{row.modeledSetCount ?? "—"}</td> : null}
          </tr>)}
        </tbody>
      </table>
    </div>
    <ul className="md:hidden">
      <li data-rankings-reference-row className="my-1 flex items-center gap-2 border-y border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]"><span aria-hidden="true">◉</span><span>Pokémon Overall Average</span><strong className="ml-auto tabular-nums text-[var(--text-primary)]">{REFERENCE_SCORE.toFixed(1)}</strong><span className="sr-only">Benchmark reference; not ranked</span></li>
      {visible.map((row, index) => <li key={row.entityId} className={`${styles.mobileRow} p-3`} data-entity-id={row.entityId}>
        <div className="grid grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-2.5">
          <strong className="text-right text-sm"><RankCell row={row} sortKey={sort.key} /></strong>
          <div className="min-w-0">{identity(row, index, true)}{showModeledSets ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{row.modeledSetCount ?? "—"} modeled sets</p> : null}</div>
          <ScoreCell column={SCORE_COLUMNS[0]} row={row} entitled={entitled} paidStatus={paidStatus} />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {COMPONENT_COLUMNS.map((column) => <div key={column.key} className="flex flex-col items-start gap-1"><span aria-hidden="true" className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{column.label}</span><ScoreCell column={column} row={row} entitled={entitled} paidStatus={paidStatus} /></div>)}
        </div>
      </li>)}
    </ul>
  </div>;
}
