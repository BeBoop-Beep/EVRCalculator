"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import TableSearchInput from "@/components/ui/TableSearchInput";
import SetIdentity from "./SetIdentity";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge";
import { chaseAccessibilityDisplay, CHASE_ACCESSIBILITY_HELP } from "./chaseAccessibilityDisplay.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { canonicalMetricRows, readChaseAccessibilitySetRanking, readFinancialSetRanking, readSetCollectorAppealRanking } from "./setMetricRankingSelectors.mjs";
import { money } from "./openingEconomicsSelector.mjs";
import styles from "./explore.module.css";

const unavailable = <span className="text-xs text-[var(--text-secondary)]">Unavailable</span>;
const percent = (value) => value === null ? null : `${value.toFixed(1)}%`;
const probability = (value) => value === null ? null : `${(value * 100).toFixed(1)}%`;

const CONFIG = {
  financial: { title: "Financial RIP rankings", description: "Which sets have the strongest monetary opening profile?", read: readFinancialSetRanking, columns: ["Typical Opening", "Modeled Return", "Chance to Beat Cost"] },
  collectorAppeal: { title: "Collector Appeal rankings", description: "Which sets have the strongest collectible appeal?", read: readSetCollectorAppealRanking, columns: ["Roster Desirability (0–100)", "Desirable Outcome Frequency"] },
  chaseAccessibility: { title: "Chase Accessibility rankings", description: "Which sets make their important chase value most reachable?", read: readChaseAccessibilitySetRanking, columns: ["Chase Depth", "Top Chase", "Top Chase Odds"] },
};

function Headline({ kind, metric }) {
  if (kind === "chaseAccessibility") { const display = chaseAccessibilityDisplay(metric.block, { setLabel: false }); return display.primary === "Unavailable" ? unavailable : <div className="text-center"><strong className="text-base tabular-nums">{display.primary}</strong>{display.detail ? <span className="block text-[10px] text-[var(--text-secondary)]">{display.detail}</span> : null}</div>; }
  return <RipScoreBadge score={metric.publicScore} tier={metric.tier} compact label={kind === "financial" ? "Financial RIP" : "Collector Appeal"} />;
}

function SupportCells({ kind, metric }) {
  if (kind === "financial") return <><td className={styles.numeric}>{metric.typicalOpening === null ? unavailable : money(metric.typicalOpening)}</td><td className={styles.numeric}>{metric.modeledReturnPercent === null ? unavailable : percent(metric.modeledReturnPercent)}</td><td className={styles.numeric}>{metric.chanceToBeatCost === null ? unavailable : probability(metric.chanceToBeatCost)}</td></>;
  if (kind === "collectorAppeal") return <><td className={styles.numeric}>{metric.rosterScore === null ? unavailable : metric.rosterScore.toFixed(1)}</td><td className={styles.numeric}>{metric.frequencyDisplayPercent !== null ? percent(metric.frequencyDisplayPercent) : metric.frequencyRawValue !== null ? probability(metric.frequencyRawValue) : unavailable}</td></>;
  return <><td className={styles.numeric}>{metric.chaseDepth === null ? unavailable : metric.chaseDepth.toFixed(2)}</td><td>{metric.chase?.name || unavailable}</td><td className={styles.numeric}>{metric.chase?.oneInPacks === null || !metric.chase ? unavailable : `1 in ${Math.round(metric.chase.oneInPacks).toLocaleString()}`}</td></>;
}

export default function SetMetricRankingsTable({ kind, targets = [], eraFilter = null, marketDate = null }) {
  const config = CONFIG[kind];
  const [query, setQuery] = useState("");
  const rows = useMemo(() => canonicalMetricRows(targets, config.read, eraFilter, query), [targets, config, eraFilter, query]);
  return <section className={`${styles.surface} set-glass-surface overflow-hidden`} data-set-metric-ranking={kind}>
    <header className="border-b border-[var(--border-subtle)] px-3 py-4 sm:px-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold text-[var(--text-primary)]">{config.title}</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">{config.description}</p></div>{marketDate ? <p className="text-xs tabular-nums text-[var(--text-secondary)]">Rankings data as of {marketDate}</p> : null}</div><TableSearchInput value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sets..." ariaLabel={`Search ${config.title}`} containerClassName="mt-3" /></header>
    {kind === "chaseAccessibility" ? <p className="px-4 pt-3 text-xs text-[var(--text-secondary)]">{CHASE_ACCESSIBILITY_HELP}</p> : null}
    {rows.length ? <><div className="hidden overflow-x-auto md:block"><table className={styles.table}><caption className="sr-only">{config.title}, ordered by canonical published rank.</caption><thead className={styles.head}><tr><th className={styles.numeric}>Rank</th><th>Set</th><th className={styles.numeric}>{kind === "financial" ? "Financial RIP" : kind === "collectorAppeal" ? "Collector Appeal" : "Chase Accessibility"}</th><th>Tier</th>{config.columns.map((column) => <th key={column} className={styles.numeric}>{column}</th>)}</tr></thead><tbody>{rows.map((target, index) => { const metric = config.read(target); return <tr key={`${target?.target_type}:${target?.target_id}`} className={styles.row}><td className={styles.numeric}>{metric.rank === null ? "—" : `#${metric.rank}`}</td><td><Link href={buildTcgSetHrefFromTarget(target)} className={styles.rowLink}><SetIdentity target={target} variant="compact" eager={index < 6} /></Link></td><td className={styles.numeric}><Headline kind={kind} metric={metric} /></td><td><RipTierMark tier={metric.tier} /></td><SupportCells kind={kind} metric={metric} /></tr>; })}</tbody></table></div>
    <div className="space-y-2 p-3 md:hidden">{rows.map((target, index) => { const metric = config.read(target); return <Link key={`${target?.target_type}:${target?.target_id}`} href={buildTcgSetHrefFromTarget(target)} className={`${styles.mobileRow} block`}><div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2"><strong className="text-right text-sm tabular-nums">{metric.rank === null ? "—" : `#${metric.rank}`}</strong><SetIdentity target={target} variant="mobileRanking" eager={index < 4} /><div className="flex items-center gap-2"><Headline kind={kind} metric={metric} /><RipTierMark tier={metric.tier} /></div></div><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--text-secondary)]">{kind === "financial" ? <><span>Typical: {metric.typicalOpening === null ? "—" : money(metric.typicalOpening)}</span><span>Return: {metric.modeledReturnPercent === null ? "—" : percent(metric.modeledReturnPercent)}</span><span>Beat cost: {metric.chanceToBeatCost === null ? "—" : probability(metric.chanceToBeatCost)}</span></> : kind === "collectorAppeal" ? <><span>Roster (0–100): {metric.rosterScore === null ? "—" : metric.rosterScore.toFixed(1)}</span><span>Desirable outcomes: {metric.frequencyDisplayPercent !== null ? percent(metric.frequencyDisplayPercent) : metric.frequencyRawValue !== null ? probability(metric.frequencyRawValue) : "—"}</span></> : <><span>Depth: {metric.chaseDepth === null ? "—" : metric.chaseDepth.toFixed(2)}</span><span>{metric.chase?.name || "Top chase unavailable"}</span><span>{metric.chase?.oneInPacks ? `1 in ${Math.round(metric.chase.oneInPacks).toLocaleString()}` : "Odds unavailable"}</span></>}</div></Link>; })}</div></> : <p role="status" className="px-4 py-8 text-sm text-[var(--text-secondary)]">No ranked sets match the current filters.</p>}
  </section>;
}
