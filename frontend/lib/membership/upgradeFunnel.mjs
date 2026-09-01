import { INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM, normalizeIndexPlan } from "../access/indexPlanAccess.mjs";

const SAFE_SOURCES = new Set(["navbar", "rankings", "rip", "opening-economics", "market-explorer", "set-market", "card-detail", "sealed-product", "chase-efficiency"]);

export const PLAN_PRESENTATION = Object.freeze({
  basic: {
    label: "Basic", tone: "neutral",
    panelClassName: "border-[var(--border-subtle)] bg-[var(--surface-page)]",
    badgeClassName: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-primary)]",
    ctaClassName: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-primary)] focus-visible:ring-[var(--accent)]",
    compactClassName: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-primary)] focus-visible:ring-[var(--accent)]",
  },
  [INDEX_PLAN_PLUS]: {
    label: "Index Plus", tone: "gold",
    panelClassName: "border-amber-300/40 bg-amber-300/[.04]",
    badgeClassName: "border-amber-300/40 bg-amber-300/10 text-amber-200",
    ctaClassName: "border-amber-300/55 bg-amber-300/10 text-amber-100 hover:bg-amber-300/15 focus-visible:ring-amber-300",
    compactClassName: "border-amber-300/45 bg-amber-300/[.08] text-amber-100 hover:bg-amber-300/12 focus-visible:ring-amber-300",
  },
  [INDEX_PLAN_PREMIUM]: {
    label: "Index Premium", tone: "purple",
    panelClassName: "border-violet-400/45 bg-violet-500/[.05] shadow-[0_0_24px_rgba(139,92,246,.10)]",
    badgeClassName: "border-violet-400/45 bg-violet-500/10 text-violet-200 shadow-[0_0_24px_rgba(139,92,246,.12)]",
    ctaClassName: "border-violet-400/60 bg-violet-500/10 text-violet-100 hover:bg-violet-500/15 focus-visible:ring-violet-400",
    compactClassName: "border-violet-400/50 bg-violet-500/[.08] text-violet-100 hover:bg-violet-500/12 focus-visible:ring-violet-400",
  },
});

export function buildIndexUpgradeHref(requiredPlan, options = {}) {
  const plan = normalizeIndexPlan(requiredPlan);
  if (!plan) return "/pricing";
  const params = new URLSearchParams({ plan });
  if (SAFE_SOURCES.has(options.source)) params.set("source", options.source);
  return `/pricing?${params.toString()}`;
}

export function planPresentation(plan) { return PLAN_PRESENTATION[normalizeIndexPlan(plan) || "basic"]; }

export function describePlanLock({ requiredPlan, currentPlan = null, source } = {}) {
  const required = normalizeIndexPlan(requiredPlan);
  const current = normalizeIndexPlan(currentPlan);
  const presentation = planPresentation(required);
  const upgrading = required === INDEX_PLAN_PREMIUM && current === INDEX_PLAN_PLUS;
  return { ...presentation, requiredPlan: required,
    headline: `Available with ${presentation.label}`,
    actionLabel: upgrading ? "Upgrade to Index Premium" : `Unlock with ${presentation.label}`,
    actionHref: buildIndexUpgradeHref(required, { source }) };
}
