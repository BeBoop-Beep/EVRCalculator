"use client";
import SetIdentity from "./SetIdentity";
import InfoPopover from "@/components/ui/InfoPopover";
import { BenchmarkReferenceRow, RankingsRipScoreBadge } from "./RankingsScorePrimitives";
import { money } from "./openingEconomicsSelector.mjs";
import styles from "./explore.module.css";

function Highlight({ label, info, onClick, children }) {
  const className = `${styles.surfaceQuiet} min-h-32 rounded-xl border border-[var(--border-subtle)] p-3 text-left`;
  const heading = <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">{label}{info ? <InfoPopover text={info} /> : null}</span>;
  if (!onClick) return <div className={className}>{heading}{children}</div>;
  return <div className={`${className} transition-colors hover:bg-[var(--surface-hover)]`}>{heading}<button type="button" onClick={onClick} className="block w-full text-left">{children}</button></div>;
}
const pending = <p className="mt-3 text-sm text-[var(--text-secondary)]">Temporarily unavailable.</p>;

export default function RankingsOverviewHighlights({ overview, onOpenTopSet, onOpenTopEra, onOpenLowestCost }) {
  const ready = overview?.status === "available", topSet = overview?.topSet, topEra = overview?.topEra;
  const lowest = overview?.lowestAveragePackCost, coverage = overview?.modeledCoverage, financial = overview?.overallFinancialRip;
  const setTarget = topSet ? { target_id: topSet.entityId, set_id: topSet.entityId, name: topSet.name, canonical_key: topSet.canonicalKey } : null;
  return <>
    <section className="mb-5" data-rankings-overview-highlights><h2 className="text-base font-semibold">At a glance</h2><div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      <Highlight label="Top Set" onClick={onOpenTopSet}>{ready && setTarget ? <div className="mt-2"><p className="text-xs font-semibold text-[var(--text-secondary)]">#1 Set to Open</p><div className="mt-2 flex min-w-0 items-center justify-between gap-2"><SetIdentity target={setTarget} variant="compact" eager /><RankingsRipScoreBadge metric={topSet.score} compact /></div></div> : pending}</Highlight>
      <Highlight label="Top Era" onClick={onOpenTopEra}>{ready && topEra ? <div className="mt-2"><p className="text-xs font-semibold text-[var(--text-secondary)]">#1 Era to Open</p><div className="mt-3 flex items-center justify-between gap-3"><p className="text-lg font-semibold leading-tight">{topEra.name}</p><RankingsRipScoreBadge metric={topEra.score} compact label="Era RIP Score" /></div></div> : pending}</Highlight>
      <Highlight label="Lowest Avg Cost / Pack" info="Lowest modeled average cost per pack; this is not a quality ranking." onClick={onOpenLowestCost}>{ready && lowest ? <div className="mt-3"><p className="text-base font-semibold">{lowest.setName}</p><p className="mt-2 text-2xl font-semibold tabular-nums">{money(lowest.averagePackCost)}</p></div> : pending}</Highlight>
      <Highlight label="Modeled Coverage">{ready && coverage ? <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled sets</dt><dd className="font-semibold">{coverage.setCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled products</dt><dd className="font-semibold">{coverage.productCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Product families</dt><dd className="font-semibold">{coverage.productFamilyCount}</dd></div></dl> : pending}</Highlight>
    </div></section>
    <section className={`${styles.surfaceQuiet} mb-5 rounded-xl border border-[var(--border-subtle)] p-4`} data-overall-financial-rip><div className="flex flex-wrap items-start justify-between gap-4"><div><span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">Overall Financial RIP <InfoPopover text="This is the absolute Financial RIP value used to compare Pokémon overall with individual Eras and Sets over time." /></span><p className="mt-2 text-4xl font-semibold tabular-nums">{financial?.absoluteScore == null ? "Unavailable" : Number(financial.absoluteScore).toFixed(2)}</p><p className="mt-1 text-[10px] text-[var(--text-secondary)]">Absolute Financial RIP · not a /10 score</p></div><BenchmarkReferenceRow reference={overview?.benchmarkReference} /></div></section>
  </>;
}
