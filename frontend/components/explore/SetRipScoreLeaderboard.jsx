"use client";

import { useMemo, useState } from "react";
import SetIdentity from "./SetIdentity";
import RankingsSearchInput from "./RankingsSearchInput";
import RankingsScoreTable from "./RankingsScoreTable";
import { canonicalMetricRows } from "./rankingsScoreTableModel.mjs";
import { scorecardSetTarget } from "@/lib/rankings/rankingsScorecardsClient.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";

export default function SetRipScoreLeaderboard({ scorecards = null, eraFilter = null }) {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => canonicalMetricRows(scorecards?.rows, "overall", query, eraFilter).map((item) => {
    const target = scorecardSetTarget(item.row);
    return { ...item, target, href: buildTcgSetHrefFromTarget(target) };
  }), [scorecards, query, eraFilter]);
  return <section data-set-rip-score-leaderboard className={`${styles.surface} set-glass-surface overflow-hidden`}>
    <header className="border-b border-[var(--border-subtle)] px-3 py-4 sm:px-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Set RIP Score rankings</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Canonical Set ranking against the Pokémon Overall Average.</p></div><span className="text-xs tabular-nums text-[var(--text-secondary)]">As of {scorecards?.marketDate || "—"}</span></div><RankingsSearchInput value={query} onChange={(event) => setQuery(event.target.value)} entity="Sets" className="mt-3" /></header>
    <RankingsScoreTable rows={rows} entityLabel="Set" scoreLabel="RIP Score" emptyMessage="No ranked sets match this search." renderIdentity={(item, index, mobile) => <SetIdentity target={item.target} variant={mobile ? "mobileRanking" : "compact"} eager={index < (mobile ? 4 : 6)} />} />
  </section>;
}
