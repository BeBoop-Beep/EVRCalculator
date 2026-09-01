"use client";
import Link from "next/link";
import { useAuth } from "@/components/AuthContext";
import { describePlanLock, planPresentation } from "@/lib/membership/upgradeFunnel.mjs";

export function PlanBadge({ plan, className = "" }) {
  const value = planPresentation(plan);
  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[.1em] ${value.badgeClassName} ${className}`}>{value.label}</span>;
}

export function PlanUpgradeLink({ requiredPlan, source, className = "" }) {
  const { user } = useAuth(); const lock = describePlanLock({ requiredPlan, currentPlan: user?.index_plan, source });
  return <Link href={lock.actionHref} className={`inline-flex min-h-10 items-center justify-center rounded-lg border px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 ${lock.ctaClassName} ${className}`}>{lock.actionLabel}</Link>;
}

export default function PlanLock({ requiredPlan, description, source, compact = false, className = "" }) {
  const { user } = useAuth(); const lock = describePlanLock({ requiredPlan, currentPlan: user?.index_plan, source });
  if (compact) return <Link href={lock.actionHref} className={`inline-flex min-h-8 items-center gap-1 rounded-md border px-2 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 ${lock.compactClassName} ${className}`}><span aria-hidden="true">🔒</span>{lock.label} · Unlock</Link>;
  return <div data-plan-lock={lock.requiredPlan} className={`rounded-xl border p-4 ${lock.panelClassName} ${className}`}><PlanBadge plan={requiredPlan}/><p className="mt-3 font-semibold text-[var(--text-primary)]">{lock.headline}</p>{description ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{description}</p> : null}<Link href={lock.actionHref} className={`mt-4 inline-flex min-h-10 items-center rounded-lg border px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 ${lock.ctaClassName}`}>{lock.actionLabel}</Link></div>;
}
