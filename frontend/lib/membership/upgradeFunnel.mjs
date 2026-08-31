import { INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM, normalizeIndexPlan } from "../access/indexPlanAccess.mjs";

const SAFE_SOURCES = new Set(["navbar", "rankings", "rip", "opening-economics", "market-explorer", "set-market", "card-detail", "sealed-product", "chase-efficiency"]);

export const PLAN_PRESENTATION = Object.freeze({
  basic: { label: "Basic", tone: "neutral", badgeClassName: "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-primary)]" },
  [INDEX_PLAN_PLUS]: { label: "Index Plus", tone: "gold", badgeClassName: "border-amber-300/40 bg-amber-300/10 text-amber-200" },
  [INDEX_PLAN_PREMIUM]: { label: "Index Premium", tone: "purple", badgeClassName: "border-violet-400/45 bg-violet-500/10 text-violet-200 shadow-[0_0_24px_rgba(139,92,246,.12)]" },
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
