"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthContext";
import InfoPopover from "@/components/ui/InfoPopover";
import { describePlanLock } from "@/components/explore/ExplorerPlanLockPanel";
import { INDEX_PLAN_PLUS, hasIndexPlusAccess } from "@/lib/access/indexPlanAccess.mjs";

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="4.5" y="8.5" width="11" height="8" rx="2" />
      <path d="M7 8.5V6a3 3 0 0 1 6 0v2.5" />
    </svg>
  );
}

export function useSetMarketSignalAccess() {
  const auth = useAuth();
  const user = auth?.user || null;
  return {
    canViewSetMarketSignals: hasIndexPlusAccess(user?.index_plan),
    user,
  };
}

export function SetMarketSignalLock({ description }) {
  const { user } = useSetMarketSignalAccess();
  const lock = describePlanLock({
    requiredPlan: INDEX_PLAN_PLUS,
    isAuthenticated: Boolean(user),
    currentPlan: user?.index_plan || null,
  });

  const actionClassName = "inline-flex min-h-7 items-center rounded-md border border-[rgba(45,212,191,0.5)] bg-[rgba(45,212,191,0.08)] px-2 text-[10px] font-semibold text-[rgb(45,212,191)]";
  return (
    <div data-set-market-signal-lock className="mt-2">
      <p className="text-[11px] leading-relaxed text-[var(--text-secondary)]">{description}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-primary)]">
          <LockIcon /> Index Plus
        </span>
        {lock.actionHref ? (
          <Link href={lock.actionHref} className={actionClassName}>{lock.actionLabel}</Link>
        ) : (
          <span className={actionClassName}>{lock.actionLabel}</span>
        )}
      </div>
    </div>
  );
}

export function MarketBreadthDonut({ breadth }) {
  const advancing = Math.max(0, Number(breadth?.advancingPercent) || 0);
  const declining = Math.max(0, Number(breadth?.decliningPercent) || 0);
  const unchanged = Math.max(0, Number(breadth?.unchangedPercent) || 0);
  const advancingEnd = Math.min(100, advancing);
  const decliningEnd = Math.min(100, advancingEnd + declining);
  const background = `conic-gradient(var(--positive) 0 ${advancingEnd}%, var(--negative) ${advancingEnd}% ${decliningEnd}%, rgba(148,163,184,0.55) ${decliningEnd}% 100%)`;
  const legend = [
    ["Advancing", advancing, "bg-[var(--positive)]"],
    ["Declining", declining, "bg-[var(--negative)]"],
    ["Unchanged", unchanged, "bg-slate-400/60"],
  ];

  return (
    <div className="mt-3 flex min-w-0 items-center gap-3 max-[430px]:flex-col" data-market-breadth-donut>
      <div
        role="img"
        aria-label={`${advancing}% advancing, ${declining}% declining, ${unchanged}% unchanged`}
        className="relative h-[92px] w-[92px] shrink-0 rounded-full"
        style={{ background }}
      >
        <div className="absolute inset-[13px] flex flex-col items-center justify-center rounded-full bg-[var(--surface-card)] text-center">
          <span className="text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">{Number(breadth.total).toLocaleString("en-US")}</span>
          <span className="mt-0.5 text-[9px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">Analyzed</span>
        </div>
      </div>
      <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 max-[430px]:w-full max-[430px]:grid-cols-3">
        {legend.map(([label, percent, color]) => (
          <div key={label} className="min-w-0">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold tabular-nums text-[var(--text-primary)]">
              <span className={`h-2 w-2 shrink-0 rounded-full ${color}`} /> {percent}%
            </p>
            <p className="truncate text-[10px] text-[var(--text-secondary)]">{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MarketBreadthSignal({ breadth, windowLabel, className = "" }) {
  const { canViewSetMarketSignals } = useSetMarketSignalAccess();
  return (
    <div data-market-breadth className={className}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Breadth</p>
        <InfoPopover text="Market Breadth shows how many comparable tracked cards advanced, declined, or were unchanged over the selected period. Cards need pricing at both period endpoints to be included." />
      </div>
      {!canViewSetMarketSignals ? (
        <SetMarketSignalLock description="See whether this Set's market move is broad or concentrated." />
      ) : breadth.available ? (
        <>
          <MarketBreadthDonut breadth={breadth} />
          <p className="mt-2 text-[10px] tabular-nums text-[var(--text-secondary)]">
            {breadth.advancing.toLocaleString("en-US")} advancing · {breadth.declining.toLocaleString("en-US")} declining · {breadth.flat.toLocaleString("en-US")} unchanged
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
            {breadth.total.toLocaleString("en-US")} cards included in breadth analysis · {windowLabel}
          </p>
        </>
      ) : (
        <p data-breadth-unavailable className="mt-2 text-[11px] text-[var(--text-secondary)]">{breadth.reason}</p>
      )}
    </div>
  );
}

export function ChaseConcentrationSignal({ concentration, formatMoney, className = "" }) {
  const { canViewSetMarketSignals } = useSetMarketSignalAccess();
  return (
    <div data-chase-concentration className={className}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Chase Concentration</p>
        <InfoPopover text="The Top 10 card-value scope as a share of the Standard card-market scope, aligned to the same date." />
      </div>
      {!canViewSetMarketSignals ? (
        <SetMarketSignalLock description="See how much of this Set's card-market value is concentrated in its Top 10." />
      ) : concentration.available ? (
        <>
          <p className="mt-2 text-2xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">{concentration.sharePercent}%</p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">Top 10 cards of card-market value</p>
          <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">Top 10 Value: {formatMoney(concentration.top10Value)}</p>
        </>
      ) : (
        <p data-concentration-unavailable className="mt-2 text-[11px] text-[var(--text-secondary)]">{concentration.reason}</p>
      )}
    </div>
  );
}
