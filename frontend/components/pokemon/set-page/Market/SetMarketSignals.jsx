"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthContext";
import InfoPopover from "@/components/ui/InfoPopover";
import { describePlanLock } from "@/components/explore/ExplorerPlanLockPanel";
import { INDEX_PLAN_PLUS, hasIndexPlusAccess } from "@/lib/access/indexPlanAccess.mjs";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";

// The neutral "unchanged" tone. Advancing/declining use the app's canonical
// market colors (the same POSITIVE_VALUE_COLOR/NEGATIVE_VALUE_COLOR every
// other delta/trend surface uses); there is no CSS custom property for them
// anywhere in globals.css, so referencing those two custom properties
// here previously made the WHOLE conic-gradient background declaration
// invalid CSS -- the browser drops an entire background value if any one of
// its var() references fails to resolve, which is why the donut ring was
// rendering with no fill at all while the plain-text percentages next to it
// (unaffected by the bad var) displayed fine.
const UNCHANGED_COLOR = "rgba(148,163,184,0.55)";

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
  // Literal color values, not var() references: there is no --positive/
  // --negative custom property defined anywhere in globals.css, and a
  // conic-gradient() with one unresolved var() drops the ENTIRE background
  // declaration rather than just that stop, which is what made this ring
  // invisible.
  const background = `conic-gradient(${POSITIVE_VALUE_COLOR} 0 ${advancingEnd}%, ${NEGATIVE_VALUE_COLOR} ${advancingEnd}% ${decliningEnd}%, ${UNCHANGED_COLOR} ${decliningEnd}% 100%)`;
  const legend = [
    ["Advancing", advancing, POSITIVE_VALUE_COLOR],
    ["Declining", declining, NEGATIVE_VALUE_COLOR],
    ["Unchanged", unchanged, UNCHANGED_COLOR],
  ];

  return (
    <div className="mx-auto mt-3 grid w-fit min-w-0 grid-cols-[96px_auto] items-center gap-4 max-[430px]:w-full max-[430px]:grid-cols-1 max-[430px]:gap-3" data-market-breadth-donut>
      <div className="flex w-24 justify-center max-[430px]:mx-auto" data-market-breadth-donut-column>
        <div
          role="img"
          aria-label={`${advancing}% advancing, ${declining}% declining, ${unchanged}% unchanged`}
          className="relative h-[92px] w-[92px] shrink-0 rounded-full"
          style={{ background }}
        >
          {/* --surface-card does not exist either; --surface-panel is the real
              token used for a raised panel surface elsewhere in the app. */}
          <div className="absolute inset-[13px] flex flex-col items-center justify-center rounded-full text-center" style={{ backgroundColor: "var(--surface-panel)" }}>
            <span className="text-lg font-semibold leading-none tabular-nums text-[var(--text-primary)]">{Number(breadth.total).toLocaleString("en-US")}</span>
            <span className="mt-0.5 text-[9px] uppercase tracking-[0.08em] text-[var(--text-secondary)]">Analyzed</span>
          </div>
        </div>
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-1.5 text-left max-[430px]:w-full max-[430px]:grid-cols-3" data-market-breadth-legend>
        {legend.map(([label, percent, color]) => (
          <div key={label} className="min-w-0">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold tabular-nums text-[var(--text-primary)]">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} /> {percent}%
            </p>
            <p className="truncate text-[10px] text-[var(--text-secondary)]">{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MarketBreadthSignal({ breadth, windowLabel, itemNoun = "cards", title = "Market Breadth", statusMessage = null, className = "" }) {
  const { canViewSetMarketSignals } = useSetMarketSignalAccess();
  return (
    <div data-market-breadth className={className}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{title}</p>
        <InfoPopover text="Market Breadth shows the share of comparable tracked items that advanced, declined, or were unchanged over the selected period. Items need valid pricing at both comparison endpoints to be included. Items without a valid comparison are shown separately as N/A." />
      </div>
      {!canViewSetMarketSignals ? (
        <SetMarketSignalLock description="See whether this Set's market move is broad or concentrated." />
      ) : statusMessage ? (
        <p data-breadth-status className="mt-2 text-[11px] text-[var(--text-secondary)]">{statusMessage}</p>
      ) : breadth.available ? (
        <>
          <MarketBreadthDonut breadth={breadth} />
          <p className="mt-2 text-[10px] tabular-nums text-[var(--text-secondary)]">
            {breadth.advancing.toLocaleString("en-US")} advancing · {breadth.declining.toLocaleString("en-US")} declining · {breadth.flat.toLocaleString("en-US")} unchanged
          </p>
          <p data-breadth-analyzed className="mt-1 text-[10px] text-[var(--text-secondary)]">
            {breadth.total.toLocaleString("en-US")} {itemNoun} included in breadth analysis
          </p>
          {breadth.excludedCount > 0 ? (
            <p data-breadth-excluded className="mt-1 text-[10px] tabular-nums text-[var(--text-secondary)]">
              {breadth.excludedCount.toLocaleString("en-US")} N/A · insufficient comparable pricing
            </p>
          ) : null}
          <p className="mt-1 text-[10px] text-[var(--text-secondary)]">
            {breadth.totalTrackedCount !== null
              ? `${breadth.totalTrackedCount.toLocaleString("en-US")} tracked ${itemNoun} total`
              : `${breadth.total.toLocaleString("en-US")} cards included in breadth analysis`} · {windowLabel}
          </p>
          {breadth.partialLabel ? (
            <p data-breadth-partial className="mt-0.5 text-[10px] italic text-[var(--text-secondary)]">
              {breadth.partialLabel}
            </p>
          ) : null}
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
