"use client";

import { useMemo, useState } from "react";
import SetIdentity from "./SetIdentity";
import RankingsSearchInput from "./RankingsSearchInput";
import RankingsScoreTable from "./RankingsScoreTable";
import { canonicalMetricRows } from "./rankingsScoreTableModel.mjs";
import { scorecardSetTarget } from "@/lib/rankings/rankingsScorecardsClient.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import styles from "./explore.module.css";

const CONFIG = {
  financial: { metric: "financial", title: "Financial RIP rankings", label: "Financial" },
  collectorAppeal: { metric: "collector", title: "Collector RIP rankings", label: "Collector" },
  chaseAccessibility: { metric: "chase", title: "Chase RIP rankings", label: "Chase" },
};

export default function SetMetricRankingsTable({ kind, scorecards = null, eraFilter = null }) {
  const config = CONFIG[kind];
  const [query, setQuery] = useState("");
  const rows = useMemo(() => canonicalMetricRows(scorecards?.rows, config.metric, query, eraFilter).map((item) => {
    const target = scorecardSetTarget(item.row);
    return { ...item, target, href: buildTcgSetHrefFromTarget(target) };
  }), [scorecards, config.metric, query, eraFilter]);
  return <section className={`${styles.surface} set-glass-surface overflow-hidden`} data-set-metric-ranking={kind}>
    <header className="border-b border-[var(--border-subtle)] px-3 py-4 sm:px-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">{config.title}</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Benchmark-centered Set scores ordered by canonical backend rank.</p></div><span className="text-xs tabular-nums text-[var(--text-secondary)]">As of {scorecards?.marketDate || "—"}</span></div><RankingsSearchInput value={query} onChange={(event) => setQuery(event.target.value)} entity="Sets" className="mt-3" /></header>
    <RankingsScoreTable rows={rows} entityLabel="Set" scoreLabel={config.label} renderIdentity={(item, index, mobile) => <SetIdentity target={item.target} variant={mobile ? "mobileRanking" : "compact"} eager={index < (mobile ? 4 : 6)} />} />
  </section>;
}
