"use client";

import { useMemo, useState } from "react";
import AnalyticsTableShell from "./AnalyticsTableShell";
import { RankingsCompactScore, RankingsRipScoreBadge } from "./RankingsScorePrimitives";
import { insertBenchmarkReference } from "./rankingsScoreTableModel.mjs";
import styles from "./explore.module.css";

const SECONDARY_METRICS = [["financial", "Financial"], ["chase", "Chase"], ["collector", "Collector"]];

function ReferenceRow({ mobile = false }) {
  if (mobile) return <li data-rankings-reference-row className="my-1 flex items-center gap-2 border-y border-[var(--border-subtle)] bg-white/[.025] px-3 py-2 text-xs text-[var(--text-secondary)]"><span aria-hidden="true">◉</span><span>Pokémon Overall Average</span><strong className="ml-auto tabular-nums text-[var(--text-primary)]">5.0</strong><span className="sr-only">Reference; no rank</span></li>;
  return <tr data-rankings-reference-row className="bg-white/[.025] text-[var(--text-secondary)]"><td className="border-y border-[var(--border-subtle)] px-2 py-3"><span className="sr-only">No rank</span></td><td className="border-y border-[var(--border-subtle)] px-2 py-3"><span className="inline-flex items-center gap-2"><span aria-hidden="true">◉</span>Pokémon Overall Average</span></td><td className="border-y border-[var(--border-subtle)] px-2 py-3 text-right"><strong className="tabular-nums text-[var(--text-primary)]">5.0</strong></td><td className="border-y border-[var(--border-subtle)] px-2 py-3" colSpan={4}><span className="sr-only">Benchmark reference; not ranked</span></td></tr>;
}

export default function EraRankings({ scorecards, onSelectEra }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (scorecards?.rows || []).filter((row) => !needle || String(row.name || "").toLowerCase().includes(needle)).sort((a, b) => Number(a.overall?.rank ?? Infinity) - Number(b.overall?.rank ?? Infinity)).map((row) => ({ ...row, id: row.entityId, metric: row.overall }));
  }, [query, scorecards]);
  const displayRows = insertBenchmarkReference(rows);
  if (!scorecards || !Array.isArray(scorecards.rows)) return <section className={`${styles.surface} rounded-xl p-5`}><h2 className="font-semibold">Era RIP Score unavailable</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">The certified Era scorecards are temporarily unavailable.</p></section>;
  return <AnalyticsTableShell title="Best Eras to Rip Right Now" info="Compare backend-certified Era RIP Scores and their financial, chase, and collector dimensions." query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search Eras…" searchLabel="Search Eras" context="Select an era to view its modeled sets." shown={rows.length} ranked={scorecards.rows.length} marketDate={scorecards.marketDate || null}>
    {!rows.length ? <p className="p-5 text-sm text-[var(--text-secondary)]">No eras match the current search.</p> : <section data-era-rankings data-rankings-score-table>
      <div className="hidden overflow-x-auto md:block"><table className={styles.table}><caption className="sr-only">Era rankings with Pokémon Overall Average reference.</caption><colgroup><col className={styles.rankingsScoreRankColumn} /><col /><col className={styles.rankingsScoreValueColumn} /><col span="3" className={styles.rankingsScoreValueColumn} /><col className={styles.rankingsScoreRankColumn} /></colgroup><thead className={styles.head}><tr><th className={styles.numeric}>Rank</th><th>Era</th><th className={styles.numeric}>Era RIP Score</th><th className={styles.numeric}>Financial</th><th className={styles.numeric}>Chase</th><th className={styles.numeric}>Collector</th><th className={styles.numeric}>Modeled Sets</th></tr></thead><tbody>{displayRows.map((item) => item.kind === "reference" ? <ReferenceRow key={item.id} /> : <tr className={styles.row} key={item.id}><td className={`${styles.numeric} text-sm font-bold`}>#{item.overall.rank}<span className="sr-only"> of {item.overall.cohortSize}</span></td><td><button type="button" className="font-semibold hover:underline" onClick={() => onSelectEra?.({ eraId: item.entityId, eraName: item.name, canonicalKey: item.canonicalKey })}>{item.name}</button></td><td className={styles.numeric}><RankingsRipScoreBadge metric={item.overall} label="Era RIP Score" compact /></td>{SECONDARY_METRICS.map(([key, label]) => <td className={styles.numeric} key={key}><RankingsCompactScore metric={item[key]} label={label} /></td>)}<td className={`${styles.numeric} tabular-nums`}>{item.modeledSetCount}</td></tr>)}</tbody></table></div>
      <ul className="md:hidden">{displayRows.map((item) => item.kind === "reference" ? <ReferenceRow key={item.id} mobile /> : <li className={`${styles.mobileRow} p-3`} key={item.id}><div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2.5"><strong className="text-right text-sm">#{item.overall.rank}</strong><div><button type="button" className="font-semibold hover:underline" onClick={() => onSelectEra?.({ eraId: item.entityId, eraName: item.name, canonicalKey: item.canonicalKey })}>{item.name}</button><p className="mt-1 text-xs text-[var(--text-secondary)]">{item.modeledSetCount} modeled sets</p></div><RankingsRipScoreBadge metric={item.overall} label="Era RIP Score" compact /></div><div className="mt-3 grid grid-cols-3 gap-2">{SECONDARY_METRICS.map(([key, label]) => <RankingsCompactScore key={key} metric={item[key]} label={label} />)}</div></li>)}</ul>
    </section>}
  </AnalyticsTableShell>;
}
