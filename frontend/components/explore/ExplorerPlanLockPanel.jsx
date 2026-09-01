"use client";
import PlanLock from "@/components/membership/PlanLock";
export { describePlanLock } from "@/lib/membership/upgradeFunnel.mjs";

export default function ExplorerPlanLockPanel({ requiredPlan, description }) {
  return <PlanLock requiredPlan={requiredPlan} description={description} source="market-explorer" className="mt-1"/>;
}
