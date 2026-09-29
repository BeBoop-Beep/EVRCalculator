"use client";

import Link from "next/link";
import { RankingsRipScoreBadge } from "./RankingsScorePrimitives";
import { insertBenchmarkReference } from "./rankingsScoreTableModel.mjs";
import styles from "./explore.module.css";

function Reference({ scoreLabel, mobile = false }) {
  const content = <><span aria-hidden="true" className="text-sm">◉</span><span className="font-medium">Pokémon Overall Average</span><strong className="ml-auto tabular-nums text-[var(--text-primary)]">5.0</strong><span className="sr-only">Reference; no rank</span></>;
  if (mobile) return <li data-rankings-reference-row className="my-1 flex items-center gap-2 border-y border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]">{content}</li>;
  return <tr data-rankings-reference-row className="bg-white/[.025] text-[var(--text-secondary)]"><td className="border-y border-[var(--border-subtle)] px-2 py-3"><span className="sr-only">No rank</span></td><td className="border-y border-[var(--border-subtle)] px-2 py-3"><span className="inline-flex items-center gap-2"><span aria-hidden="true">◉</span><span className="font-medium">Pokémon Overall Average</span></span></td><td className="border-y border-[var(--border-subtle)] px-2 py-3 text-right"><strong className="tabular-nums text-[var(--text-primary)]">5.0</strong><span className="sr-only"> {scoreLabel} reference</span></td></tr>;
}

export default function RankingsScoreTable({ rows = [], entityLabel = "Set", scoreLabel = "RIP Score", renderIdentity, emptyMessage = "No rankings match the current filters." }) {
  const displayRows = insertBenchmarkReference(rows);
  if (!rows.length) return <p className="p-5 text-sm text-[var(--text-secondary)]">{emptyMessage}</p>;
  return <div data-rankings-score-table>
    <div className="hidden overflow-x-auto md:block">
      <table className={styles.table}><caption className="sr-only">{entityLabel} rankings with Pokémon Overall Average reference.</caption>
        <colgroup><col className={styles.rankingsScoreRankColumn} /><col /><col className={styles.rankingsScoreValueColumn} /></colgroup>
        <thead className={styles.head}><tr><th scope="col" className={styles.numeric}>Rank</th><th scope="col">{entityLabel}</th><th scope="col" className={styles.numeric}>{scoreLabel}</th></tr></thead>
        <tbody>{displayRows.map((item, index) => item.kind === "reference" ? <Reference key={item.id} scoreLabel={scoreLabel} /> : <tr key={item.id} className={styles.row}><td className={`${styles.numeric} text-sm font-bold`}>{item.metric?.rank == null ? "—" : `#${item.metric.rank}`}<span className="sr-only"> of {item.metric?.cohortSize}</span></td><td>{item.href ? <Link href={item.href} className={styles.rowLink}>{renderIdentity(item, index)}</Link> : renderIdentity(item, index)}</td><td className={styles.numeric}><RankingsRipScoreBadge metric={item.metric} label={scoreLabel} compact /></td></tr>)}</tbody>
      </table>
    </div>
    <ul className="md:hidden">{displayRows.map((item, index) => item.kind === "reference" ? <Reference key={item.id} mobile scoreLabel={scoreLabel} /> : <li key={item.id}>{item.href ? <Link href={item.href} className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2.5`}><strong className="text-right text-sm">{item.metric?.rank == null ? "—" : `#${item.metric.rank}`}</strong>{renderIdentity(item, index, true)}<RankingsRipScoreBadge metric={item.metric} label={scoreLabel} compact /></Link> : <div className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2.5`}><strong className="text-right text-sm">{item.metric?.rank == null ? "—" : `#${item.metric.rank}`}</strong>{renderIdentity(item, index, true)}<RankingsRipScoreBadge metric={item.metric} label={scoreLabel} compact /></div>}</li>)}</ul>
  </div>;
}
