"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import SetIdentity from "./SetIdentity";
import BenchmarkScoreBadge from "./BenchmarkScoreBadge";
import { benchmarkMetric, formatBenchmarkFreshness } from "./ripBenchmarkPresentation.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";

function entityId(target) { return target?.target_id || target?.setId || target?.id; }
function canonicalSetOrder(left, right, benchmark) {
  const leftRank = benchmarkMetric(benchmark?.rows, "set", entityId(left), "overall").rank;
  const rightRank = benchmarkMetric(benchmark?.rows, "set", entityId(right), "overall").rank;
  if (leftRank !== null && rightRank !== null && leftRank !== rightRank) return leftRank - rightRank;
  if (leftRank !== null) return -1;
  if (rightRank !== null) return 1;
  return String(left?.name || "").localeCompare(String(right?.name || ""));
}

export default function SetRipScoreLeaderboard({ targets = [], benchmark = null, eraFilter = null, marketDate = null }) {
  const [searchQuery, setSearchQuery] = useState("");
  const rows = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    const era = String(eraFilter || "").trim().toLocaleLowerCase();
    return [...targets].sort((a, b) => canonicalSetOrder(a, b, benchmark)).filter((target) => {
      if (era && String(target?.era || "").trim().toLocaleLowerCase() !== era) return false;
      return !query || String(target?.name || "").toLocaleLowerCase().includes(query);
    });
  }, [targets, benchmark, eraFilter, searchQuery]);

  return (
    <section data-set-rip-score-leaderboard className={`${styles.surface} set-glass-surface overflow-hidden`} aria-labelledby="set-rip-score-title">
      <header className="border-b border-[var(--border-subtle)] px-3 py-4 sm:px-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="set-rip-score-title" className="text-lg font-semibold text-[var(--text-primary)]">Set RIP Score rankings</h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">Which sets rank strongest by Set RIP Score?</p>
          </div>
          {formatBenchmarkFreshness(benchmark?.freshness) ? <p className="text-xs tabular-nums text-[var(--text-secondary)]">{formatBenchmarkFreshness(benchmark.freshness)}</p> : null}
        </div>
        <div className="mt-3 max-w-md">
          <TableSearchInput value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} ariaLabel="Search Set RIP Score rankings" placeholder="Search sets..." />
        </div>
      </header>

      {rows.length ? (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className={styles.table}>
              <caption className="sr-only">Sets ranked by canonical Set RIP Score.</caption>
              <colgroup><col style={{ width: "6rem" }} /><col /><col style={{ width: "14rem" }} /><col style={{ width: "10rem" }} /><col style={{ width: "8rem" }} /></colgroup>
              <thead className={styles.head}><tr><th scope="col" className={styles.numeric}>Rank</th><th scope="col">Set</th><th scope="col">Era</th><th scope="col" className={styles.numeric}>RIP Score</th></tr></thead>
              <tbody>{rows.map((target, index) => {
                const rip = benchmarkMetric(benchmark?.rows, "set", entityId(target), "overall");
                return <tr key={`${target?.target_type}:${target?.target_id}`} className={styles.row}>
                  <td className={styles.numeric}>{rip.rank === null ? "—" : `#${rip.rank}`}</td>
                  <td><Link href={buildTcgSetHrefFromTarget(target)} className={styles.rowLink}><SetIdentity variant="compact" target={target} eager={index < 6} /></Link></td>
                  <td className="text-sm text-[var(--text-secondary)]">{target?.era || "—"}</td>
                  <td className={styles.numeric}><BenchmarkScoreBadge metric={rip} label="RIP Score" /></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          <div className="space-y-2 p-3 md:hidden">{rows.map((target, index) => {
            const rip = benchmarkMetric(benchmark?.rows, "set", entityId(target), "overall");
            return <Link key={`${target?.target_type}:${target?.target_id}`} href={buildTcgSetHrefFromTarget(target)} className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2.5`}>
              <span className="text-right text-sm font-bold tabular-nums">{rip.rank === null ? "—" : `#${rip.rank}`}</span>
              <SetIdentity variant="mobileRanking" target={target} eager={index < 4} />
              <BenchmarkScoreBadge metric={rip} compact label="RIP Score" />
            </Link>;
          })}</div>
        </>
      ) : <p className="p-5 text-sm text-[var(--text-secondary)]">No ranked sets match this search.</p>}
    </section>
  );
}
