import { formatMinorAmount } from "./billingPricing.mjs";

export const PLAN_LABELS = Object.freeze({ basic: "Basic", plus: "Index Plus", premium: "Index Premium" });
const KNOWN_STATUSES = new Set(["trialing","active","past_due","incomplete","incomplete_expired","unpaid","canceled","paused"]);

export function normalizePlan(plan) { return plan === "plus" || plan === "premium" ? plan : "basic"; }
export function planLabel(plan) { return PLAN_LABELS[normalizePlan(plan)]; }
export function statusPresentation(status, cancelAtPeriodEnd = false) {
  if (!status || !KNOWN_STATUSES.has(status)) return { label: "Billing status unavailable", severity: "neutral" };
  if (status === "active" && cancelAtPeriodEnd) return { label: "Scheduled to end", severity: "warning" };
  return ({ trialing:["Trial","info"], active:["Active","success"], past_due:["Payment issue","warning"],
    unpaid:["Payment required","danger"], canceled:["Subscription ended","neutral"], paused:["Billing paused","warning"],
    incomplete:["Subscription setup incomplete","warning"], incomplete_expired:["Subscription setup expired","neutral"]
  }[status] || ["Billing status unavailable","neutral"]).reduce((result, value, index) => ({ ...result, [index ? "severity" : "label"]: value }), {});
}
export function formatBillingDate(value, locale) {
  if (!value) return null;
  const date = new Date(value); if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { year:"numeric", month:"long", day:"numeric" }).format(date);
}
export function billingMessage(status, { cancelAtPeriodEnd=false, currentPeriodEnd=null, effectivePlan=null } = {}) {
  const date = formatBillingDate(currentPeriodEnd);
  if (status === "active" && cancelAtPeriodEnd) return date ? `Your subscription is scheduled to end on ${date}. Access remains active until then.` : "Your subscription is scheduled to end. Access remains active until the paid period finishes.";
  if (status === "active") return date ? `Your subscription renews on ${date}.` : "Your subscription is active.";
  if (status === "trialing") return date ? `Your trial continues through ${date}.` : "Your trial is active.";
  if (status === "past_due") return "Your membership remains active while payment recovery is in progress. Update your payment method to avoid losing access.";
  if (status === "unpaid") return effectivePlan ? `Stripe billing requires attention. Your current inDex access remains ${planLabel(effectivePlan)}.` : "Your paid membership is no longer active.";
  if (status === "canceled") return "Your Stripe subscription has ended.";
  if (status === "paused") return "Your Stripe billing is currently paused.";
  if (status === "incomplete" || status === "incomplete_expired") return "Your subscription setup did not complete.";
  return null;
}
export function canManageSubscription(status) { return Boolean(status); }
export function selectableOffers(dto) { return dto?.billingManaged ? [] : Array.isArray(dto?.purchasableOfferKeys) ? dto.purchasableOfferKeys : []; }
export function offerPlan(key) { return key?.startsWith("premium_") ? "premium" : key?.startsWith("plus_") ? "plus" : null; }
export function offerInterval(key) { return key?.endsWith("_annual") ? "Annual" : key?.endsWith("_monthly") ? "Monthly" : ""; }

export function pendingChangeCopy(status) {
  if (!status || status.pendingChangeState !== "scheduled") {
    return null;
  }
  const planName = planLabel(status.pendingPlan);
  const date = formatBillingDate(status.pendingChangeEffectiveAt != null ? status.pendingChangeEffectiveAt * 1000 : status.pendingChangeEffectiveAt);
  return `Changes to ${planName} on ${date}`;
}

export function upgradeConfirmationCopy({ amountDueNow, currency, nextRenewalAt }) {
  const dueNowLabel = formatMinorAmount(amountDueNow, currency);
  const renewalDate = formatBillingDate(nextRenewalAt != null ? nextRenewalAt * 1000 : nextRenewalAt);
  return {
    dueNowLabel,
    bodyLines: [
      "Your new membership begins immediately after successful payment.",
      `Next renewal: ${renewalDate}`,
      "Index Premium then continues to renew automatically at your selected billing interval until canceled.",
      "Cancel before a renewal to avoid future charges. Ordinary cancellation normally takes effect at the end of the current paid period and does not automatically create a prorated refund.",
    ],
  };
}

export function downgradeConfirmationCopy({ currentPlanUntil }) {
  const untilDate = formatBillingDate(currentPlanUntil != null ? currentPlanUntil * 1000 : currentPlanUntil);
  return {
    bodyLines: [
      `You'll keep Index Premium until ${untilDate}.`,
      "Index Plus begins after that.",
      "No charge today.",
      "After the change, Index Plus continues to renew automatically at your selected billing interval until canceled.",
      "Cancel before a renewal to avoid future charges. Ordinary cancellation normally takes effect at the end of the current paid period and does not automatically create a prorated refund.",
    ],
  };
}
