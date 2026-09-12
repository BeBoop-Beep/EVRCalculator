"use client";

import SetIdentity from "./SetIdentity";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge";
import { readPublicSetRip } from "./setRipPublicPresentation.mjs";
import { eraStrengthRows } from "./eraSetStrengthSelector.mjs";
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

export default function RankingsOverviewHighlights({ setsState, eraState, openingEconomics, onOpenTopSet, onOpenTopEra, onOpenLowestCost }) {
  const topSet = setsState?.status === "ready" ? setsState.targets.find((target) => readPublicSetRip(target).rank === 1) || null : null;
  const topSetRip = topSet ? readPublicSetRip(topSet) : null;
  const topEra = eraState?.status === "ready" ? eraStrengthRows(eraState.contract).find((era) => era.rank === 1) || null : null;
  const publicSetEconomics = Array.isArray(openingEconomics?.sets) ? openingEconomics.sets : [];
  const lowestCost = publicSetEconomics.reduce((best, row) => Number.isFinite(Number(row?.averageCostPerPack)) && (!best || Number(row.averageCostPerPack) < Number(best.averageCostPerPack)) ? row : best, null);
  const global = openingEconomics?.global || null;

  return <section className="mb-5" data-rankings-overview-highlights>
    <h2 className="text-base font-semibold text-[var(--text-primary)]">At a glance</h2>
    <p className="mt-1 text-xs text-[var(--text-secondary)]">Public highlights from the latest Rankings and Opening Economics publications.</p>
    <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
      <Highlight label="Top Set" onClick={onOpenTopSet}>{topSet ? <div className="mt-2 flex items-center justify-between gap-2"><div className="min-w-0"><p className="text-xs font-semibold text-[var(--text-secondary)]">#1 Set RIP ranked Set</p><SetIdentity target={topSet} variant="compact" eager /></div><div className="flex flex-none items-center gap-1"><RipScoreBadge score={topSetRip.publicScore} tier={topSetRip.tier} compact label="Set RIP" /><RipTierMark tier={topSetRip.tier} /></div></div> : <Pending failed={["error", "unavailable"].includes(setsState?.status)} noun="Top Set" />}</Highlight>
      <Highlight label="Top Era" onClick={onOpenTopEra}>{topEra ? <div className="mt-3"><p className="text-lg font-semibold text-[var(--text-primary)]">{topEra.eraName}</p><div className="mt-2 flex items-center gap-2"><span className="text-sm font-bold tabular-nums">#1</span><RipScoreBadge score={topEra.score} tier={topEra.tier} compact label="Set Strength" /><RipTierMark tier={topEra.tier} /></div>{topEra.strongestSet?.setName ? <p className="mt-2 text-xs text-[var(--text-secondary)]">Strongest Set: <span className="text-[var(--text-primary)]">{topEra.strongestSet.setName}</span></p> : null}</div> : <Pending failed={["error", "unavailable"].includes(eraState?.status)} noun="Top Era" />}</Highlight>
      <Highlight label="Lowest Avg Cost / Pack" onClick={onOpenLowestCost}>{lowestCost ? <div className="mt-3"><p className="text-base font-semibold text-[var(--text-primary)]">{lowestCost.setName}</p><p className="mt-2 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{money(lowestCost.averageCostPerPack)}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">Lowest modeled average cost per pack; not a quality ranking.</p></div> : <Pending failed={openingEconomics?.status === "unavailable"} noun="Set cost data" />}</Highlight>
      <Highlight label="Modeled Coverage" onClick={undefined}>{global ? <dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled sets</dt><dd className="font-semibold tabular-nums">{global.setCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Modeled products</dt><dd className="font-semibold tabular-nums">{global.productSkuCount}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-secondary)]">Product families</dt><dd className="font-semibold tabular-nums">{global.productFamilyCount}</dd></div></dl> : <Pending failed noun="Coverage" />}</Highlight>
    </div>
  </section>;
}
