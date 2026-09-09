"use client";
import PlanLock from "@/components/membership/PlanLock";
import Link from "next/link";
export { describePlanLock } from "@/lib/membership/upgradeFunnel.mjs";

export default function ExplorerPlanLockPanel({ requiredPlan, description, isAuthenticated = false }) {
  if (!isAuthenticated) return <div className="mt-1 rounded-xl border border-[var(--border-subtle)] p-4"><p className="font-semibold text-[var(--text-primary)]">Not authenticated</p><p className="mt-1 text-sm text-[var(--text-secondary)]">Sign in to continue. {description}</p><Link data-market-query-sign-in href="/login" className="mt-3 inline-flex min-h-10 items-center rounded-lg border border-[var(--border-subtle)] px-4 text-sm font-semibold">Sign in</Link></div>;
  return <PlanLock requiredPlan={requiredPlan} description={description} source="market-explorer" className="mt-1"/>;
}
