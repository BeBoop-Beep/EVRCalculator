"use client";
import Link from "next/link";
import { useAuth } from "@/components/AuthContext";
import { normalizeIndexPlan } from "@/lib/access/indexPlanAccess.mjs";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";

export default function MembershipNavLink({ mobile = false }) {
  const { user } = useAuth(); const plan = normalizeIndexPlan(user?.index_plan); const value = planPresentation(plan);
  const href = plan ? "/account-settings?section=billing" : "/pricing";
  const label = plan ? value.label : "Upgrade";
  return <Link data-membership-nav href={href} className={mobile ? "block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)]" : `inline-flex min-h-9 items-center rounded-lg border px-3 text-sm font-semibold ${plan ? value.badgeClassName : "border-amber-300/35 bg-amber-300/10 text-amber-200"}`}>{label}</Link>;
}
