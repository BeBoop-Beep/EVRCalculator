"use client";

import { useMemo, useState } from "react";
import SetIdentity from "./SetIdentity";
import RankingsSearchInput from "./RankingsSearchInput";
import BenchmarkEntityScoreTable from "./BenchmarkEntityScoreTable";
import { mergeScorecardRows } from "./unifiedScoreTableModel.mjs";
import { scorecardSetTarget } from "@/lib/rankings/rankingsScorecardsClient.mjs";
import { usePaidScorecards } from "@/lib/rankings/usePaidScorecards";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";

export default function SetRipScoreLeaderboard({ scorecards = null, eraFilter = null, sessionCache = null, canViewRankingsIntelligence = false }) {
  const [query, setQuery] = useState("");
  const paid = usePaidScorecards("set", { sessionCache, entitled: canViewRankingsIntelligence });
  const merged = useMemo(() => mergeScorecardRows(scorecards, canViewRankingsIntelligence ? paid.scorecards : null), [scorecards, canViewRankingsIntelligence, paid.scorecards]);
  return <section data-set-rip-score-leaderboard className={`${styles.surface} set-glass-surface overflow-hidden`}>
    <header className="border-b border-[var(--border-subtle)] px-3 py-4 sm:px-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Set RIP Score rankings</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Canonical Set ranking against the Pokémon Overall Average.</p></div><span className="text-xs tabular-nums text-[var(--text-secondary)]">As of {merged.marketDate || "—"}</span></div><RankingsSearchInput value={query} onChange={(event) => setQuery(event.target.value)} entity="Sets" className="mt-3" /></header>
    <BenchmarkEntityScoreTable
      entityLabel="Set"
      rows={merged.rows}
      query={query}
      eraFilter={eraFilter}
      entitled={canViewRankingsIntelligence}
      paidStatus={paid.status}
      emptyMessage="No ranked sets match this search."
      getHref={(row) => buildTcgSetHrefFromTarget(scorecardSetTarget(row))}
      renderIdentity={(row, index, mobile) => <SetIdentity target={scorecardSetTarget(row)} variant={mobile ? "mobileRanking" : "compact"} eager={index < (mobile ? 4 : 6)} />}
    />
  </section>;
}
