"use client";

import SetIdentity from "./SetIdentity";
import BenchmarkScoreBadge from "./BenchmarkScoreBadge";
import { benchmarkMetric } from "./ripBenchmarkPresentation.mjs";
import { money } from "./openingEconomicsSelector.mjs";
import styles from "./explore.module.css";

function Highlight({ label, onClick, children }) {
  const className = `${styles.surfaceQuiet} min-h-32 rounded-xl border border-[var(--border-subtle)] p-3 text-left`;
  const content = <><span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">{label}</span>{children}</>;
  return onClick ? <button type="button" onClick={onClick} className={`${className} transition-colors hover:bg-[var(--surface-hover)]`}>{content}</button> : <div className={className}>{content}</div>;
}

function Pending({ failed, noun }) {
  return <p className="mt-3 text-sm text-[var(--text-secondary)]">{failed ? `${noun} is temporarily unavailable.` : `Loading ${noun.toLowerCase()}…`}</p>;
}

function TopSetHighlight({ target, metric }) {
  return <div className="mt-2">
    <p className="text-xs font-semibold text-[var(--text-secondary)]">#1 Set to Open</p>
    <div className="mt-2 flex min-w-0 items-center justify-between gap-2">
      <SetIdentity target={target} variant="compact" eager />
      <BenchmarkScoreBadge metric={metric} compact label="RIP Score" />
    </div>
  </div>;
}

function TopEraHighlight({ era, metric }) {
  return <div className="mt-2">
    <p className="text-xs font-semibold text-[var(--text-secondary)]">#1 Era to Open</p>
    <div className="mt-3 flex min-w-0 items-center justify-between gap-3">
      <p className="min-w-0 text-lg font-semibold leading-tight text-[var(--text-primary)]">{era.eraName}</p>
      <BenchmarkScoreBadge metric={metric} compact label="Era RIP Score" />
    </div>
  </div>;
}

export default function RankingsOverviewHighlights({ setsState, eraState, openingEconomics, onOpenTopSet, onOpenTopEra, onOpenLowestCost }) {
  const setMetrics = (setsState?.targets || []).map((target) => ({ target, metric: benchmarkMetric(setsState?.benchmark?.rows, "set", target?.target_id || target?.setId || target?.id, "overall") }));
  const topSetEntry = setsState?.status === "ready" ? setMetrics.find(({ metric }) => metric.rank === 1) || null : null;
  const topSet = topSetEntry?.target || null;
  const topSetRip = topSetEntry?.metric || null;
  const eraEntries = (eraState?.contract?.eras || []).map((era) => ({ era, metric: benchmarkMetric(eraState?.benchmark?.rows, "era", era?.eraId, "overall") }));
  const topEraEntry = eraState?.status === "ready" ? eraEntries.find(({ metric }) => metric.rank === 1) || null : null;
  const topEra = topEraEntry?.era || null;
  const publicSetEconomics = Array.isArray(openingEconomics?.sets) ? openingEconomics.sets : [];
  const lowestCost = publicSetEconomics.reduce((best, row) => Number.isFinite(Number(row?.averageCostPerPack)) && (!best || Number(row.averageCostPerPack) < Number(best.averageCostPerPack)) ? row : best, null);
  const global = openingEconomics?.global || null;

  return <section className="mb-5" data-rankings-overview-highlights>
    <h2 className="text-base font-semibold text-[var(--text-primary)]">At a glance</h2>
    <p className="mt-1 text-xs text-[var(--text-secondary)]">Public highlights from the latest Rankings and Opening Economics publications.</p>
    <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
      <Highlight label="Top Set" onClick={onOpenTopSet}>{topSet ? <TopSetHighlight target={topSet} metric={topSetRip} /> : <Pending failed={["error", "unavailable"].includes(setsState?.status)} noun="Top Set" />}</Highlight>
      <Highlight label="Top Era" onClick={onOpenTopEra}>{topEra ? <TopEraHighlight era={topEra} metric={topEraEntry.metric} /> : <Pending failed={["error", "unavailable", "locked"].includes(eraState?.status)} noun="Top Era" />}</Highlight>
      <Highlight label="Lowest Avg Cost / Pack" onClick={onOpenLowestCost}>{lowestCost ? <div className="mt-3"><p className="text-base font-semibold text-[var(--text-primary)]">{lowestCost.setName}</p><p className="mt-2 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{money(lowestCost.averageCostPerPack)}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">Lowest modeled average cost per pack; not a quality ranking.</p></div> : <Pending failed={openingEconomics?.status === "unavailable"} noun="Set cost data" />}</Highlight>
      <Highlight label="Modeled Coverage" onClick={undefined}>{global ? <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled sets</dt><dd className="font-semibold tabular-nums">{global.setCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled products</dt><dd className="font-semibold tabular-nums">{global.productSkuCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Product families</dt><dd className="font-semibold tabular-nums">{global.productFamilyCount}</dd></div></dl> : <Pending failed noun="Coverage" />}</Highlight>
    </div>
  </section>;
}
