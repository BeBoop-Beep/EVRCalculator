"use client";

import { useMemo, useState } from "react";
import AnalyticsTableShell from "./AnalyticsTableShell";
import BenchmarkEntityScoreTable from "./BenchmarkEntityScoreTable";
import { filterScoreRows, mergeScorecardRows } from "./unifiedScoreTableModel.mjs";
import { usePaidScorecards } from "@/lib/rankings/usePaidScorecards";

export default function EraRankings({ scorecards, onSelectEra, sessionCache = null, canViewRankingsIntelligence = false }) {
  const [query, setQuery] = useState("");
  const paid = usePaidScorecards("era", { sessionCache, entitled: canViewRankingsIntelligence });
  const merged = useMemo(() => mergeScorecardRows(scorecards, canViewRankingsIntelligence ? paid.scorecards : null), [scorecards, canViewRankingsIntelligence, paid.scorecards]);
  const shown = useMemo(() => filterScoreRows(merged.rows, { query }).length, [merged.rows, query]);
  if (!scorecards || !Array.isArray(scorecards.rows)) return <section className="rounded-xl p-5"><h2 className="font-semibold">Era RIP Score unavailable</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">The certified Era scorecards are temporarily unavailable.</p></section>;
  return <AnalyticsTableShell title="Best Eras to Rip Right Now" info="Compare backend-certified Era RIP Scores and their financial, collector appeal, and chase dimensions." query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search Eras…" searchLabel="Search Eras" context="Select an era to view its modeled sets." shown={shown} ranked={merged.rows.length} marketDate={merged.marketDate}>
    <section data-era-rankings>
      <BenchmarkEntityScoreTable
        entityLabel="Era"
        rows={merged.rows}
        query={query}
        entitled={canViewRankingsIntelligence}
        paidStatus={paid.status}
        showModeledSets
        emptyMessage="No eras match the current search."
        renderIdentity={(row) => <button type="button" className="font-semibold hover:underline" onClick={() => onSelectEra?.({ eraId: row.entityId, eraName: row.name, canonicalKey: row.canonicalKey })}>{row.name}</button>}
      />
    </section>
  </AnalyticsTableShell>;
}
