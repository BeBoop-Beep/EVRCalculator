import { planLabel } from "@/lib/billing/billingPresentation.mjs";
export default function MembershipPlanBadge({ plan }) {
  return <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">{planLabel(plan)}</span>;
}
