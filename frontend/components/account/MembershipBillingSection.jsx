"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthContext";
import MembershipPlanBadge from "./MembershipPlanBadge";
import { createCheckoutSession, createCustomerPortalSession, getBillingStatus } from "@/lib/billing/billingClient.mjs";
import { billingMessage, offerInterval, offerPlan, planLabel, selectableOffers, statusPresentation } from "@/lib/billing/billingPresentation.mjs";
import { formatMinorAmount, planPricingSummary, pricingByOfferKey } from "@/lib/billing/billingPricing.mjs";

const PLAN_COPY = {
  plus: "Deeper statistics, opening economics, market breadth, pull odds, acquisition milestones, prepared intelligence, and single-axis market research.",
  premium: "Everything in Plus, with Chase Efficiency and advanced decision tools for choosing the best chase, opening, and market route.",
};

export default function MembershipBillingSection() {
  const router = useRouter(); const { refreshUser } = useAuth();
  const [status, setStatus] = useState(null); const [loading, setLoading] = useState(true);
  const [action, setAction] = useState(null); const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setStatus(await getBillingStatus()); await refreshUser(); }
    catch (e) { if (e?.status === 401) { router.push("/login"); return; } setError("Membership information is temporarily unavailable. Your profile settings are unaffected."); }
    finally { setLoading(false); }
  }, [router, refreshUser]);
  useEffect(() => { load(); }, [load]);
  const offers = useMemo(() => selectableOffers(status), [status]);
  const pricing = useMemo(() => pricingByOfferKey(status), [status]);

  async function checkout(offerKey) {
    if(action) return; setAction(offerKey); setError("");
    try { const result = await createCheckoutSession(offerKey); window.location.assign(result.checkoutUrl); }
    catch (e) { setError(e?.code === "BILLING_OFFER_NOT_CONFIGURED" ? "That membership option is not currently available." : e?.status === 401 ? "Your session expired. Sign in again to continue." : "Unable to start secure checkout. Please try again."); setAction(null); }
  }
  async function portal() {
    if(action) return; setAction("portal"); setError("");
    try { const result = await createCustomerPortalSession(); window.location.assign(result.portalUrl); }
    catch { setError("Unable to open subscription management. Please try again."); setAction(null); }
  }
  function changePlan() {
    const plan = status?.billingPlan || status?.effectivePlan || "plus";
    const interval = status?.offerKey?.endsWith("_monthly") ? "month" : "year";
    router.push(`/pricing?plan=${encodeURIComponent(plan)}&interval=${interval}`);
  }
  const presentation = statusPresentation(status?.subscriptionStatus, status?.cancelAtPeriodEnd);
  const message = billingMessage(status?.subscriptionStatus, status || {});
  return <section id="billing" aria-labelledby="billing-heading" className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6 sm:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 id="billing-heading" className="text-xl font-semibold text-[var(--text-primary)]">Membership &amp; Billing</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Manage your inDex access and subscription.</p></div>{status ? <MembershipPlanBadge plan={status.effectivePlan}/> : null}</div>
    {loading ? <p className="mt-6 text-sm text-[var(--text-secondary)]" role="status">Loading membership information...</p> : null}
    {!loading && status ? <div className="mt-6 space-y-6">
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4"><p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">Current Plan</p><p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{planLabel(status.effectivePlan)}</p>
        {status.billingManaged ? <><p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{presentation.label}</p>{status.billingPlan && status.billingPlan !== status.effectivePlan ? <p className="mt-1 text-sm text-[var(--text-secondary)]">Stripe subscription: {planLabel(status.billingPlan)}. Current access includes {planLabel(status.effectivePlan)}.</p> : null}{message ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{message}</p> : null}<div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={changePlan} disabled={Boolean(action)} className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60">Change Plan</button><button type="button" onClick={portal} disabled={Boolean(action)} className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-60">{action === "portal" ? "Opening..." : "Manage Subscription"}</button></div></> : status.accessManagedByIndex ? <p className="mt-2 text-sm text-[var(--text-secondary)]">Access managed by inDex.</p> : <p className="mt-2 text-sm text-[var(--text-secondary)]">Your account includes public inDex tools and insights.</p>}</div>
      <div className="grid gap-4 md:grid-cols-2">{["plus", "premium"].map(plan => {
        const summary = planPricingSummary(status, plan);
        return <article key={plan} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5"><h3 className="font-semibold text-[var(--text-primary)]">{planLabel(plan)}</h3><p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{PLAN_COPY[plan]}</p><div className="mt-4 flex flex-wrap gap-2">{offers.filter(key => offerPlan(key) === plan).map(key => {
          const offer = pricing[key]; const amount = offer ? formatMinorAmount(offer.unitAmount, offer.currency) : null;
          return <button key={key} type="button" onClick={() => checkout(key)} disabled={Boolean(action)} className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] disabled:opacity-60">{action === key ? "Starting..." : amount ? `${amount} / ${offer.billingInterval}` : `Choose ${offerInterval(key)}`}</button>;
        })}</div>{summary.annualSummary ? <p className="mt-3 text-sm font-semibold text-emerald-300">Annual saves {formatMinorAmount(summary.annualSummary.annualSavings, summary.annualSummary.currency)} ({summary.annualSummary.annualDiscountPercent}%). Effective {formatMinorAmount(summary.annualSummary.effectiveMonthlyAnnualRate, summary.annualSummary.currency)} / month.</p> : null}{!summary.monthly && !summary.annual ? <p className="mt-4 text-sm font-medium text-[var(--text-secondary)]">Pricing pending — not yet available.</p> : null}</article>;
      })}</div>
    </div> : null}
    {error ? <p className="mt-4 text-sm text-red-300" role="alert">{error}</p> : null}
  </section>;
}
