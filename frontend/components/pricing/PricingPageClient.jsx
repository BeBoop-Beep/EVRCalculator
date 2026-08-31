"use client";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthContext";
import { createCheckoutSession, createCustomerPortalSession, getBillingCatalog, getBillingStatus } from "@/lib/billing/billingClient.mjs";
import { formatMinorAmount, planPricingSummary } from "@/lib/billing/billingPricing.mjs";
import { normalizeIndexPlan } from "@/lib/access/indexPlanAccess.mjs";
import { PlanBadge } from "@/components/membership/PlanLock";

const BASIC = ["Public rankings and market pulse", "Set and card discovery", "Portfolio and collection tools"];
const PLUS = ["Product RIP rankings", "Detailed EV, recovery, and opening economics", "Set pack economics", "Era pack economics", "Market breadth", "Card pull odds", "Acquisition milestones", "Prepared Market Explorer intelligence", "Single-axis custom markets"];
const PREMIUM = ["Everything in Index Plus", "Chase Efficiency ranking", "Best chase opening route", "Chase-vs-buy economics", "Global, era, set, and rarity chase rankings", "Multi-axis compound markets", "Pokémon-specific market construction", "Custom ranked market composition"];

function FeatureList({ items }) { return <ul className="mt-6 space-y-3 text-sm text-[var(--text-secondary)]">{items.map((item) => <li key={item} className="flex gap-2"><span aria-hidden="true" className="text-[var(--accent)]">✓</span><span>{item}</span></li>)}</ul>; }

function PaidCard({ plan, summary, interval, emphasized, status, onAction, pending }) {
  const offer = interval === "year" ? summary.annual : summary.monthly;
  const annual = summary.annualSummary;
  const current = normalizeIndexPlan(status?.effectivePlan) === plan;
  const managed = Boolean(status?.billingManaged);
  const purchasable = Boolean(offer?.purchasable);
  let label = "Coming Soon", disabled = true;
  if (current) label = "Current Plan";
  else if (managed) { label = "Manage / Upgrade Membership"; disabled = false; }
  else if (purchasable) { label = status ? `Upgrade to Index ${plan === "plus" ? "Plus" : "Premium"}` : `Get Index ${plan === "plus" ? "Plus" : "Premium"}`; disabled = false; }
  return <article data-pricing-plan={plan} data-pricing-emphasized={emphasized ? "true" : "false"} className={`rounded-2xl border p-6 ${plan === "plus" ? "border-amber-300/35 bg-amber-300/[.04]" : "border-violet-400/40 bg-violet-500/[.05] shadow-[0_0_36px_rgba(139,92,246,.10)]"} ${emphasized ? "ring-2 ring-offset-2 ring-offset-[var(--surface-page)] " + (plan === "plus" ? "ring-amber-300/60" : "ring-violet-400/60") : ""}`}><PlanBadge plan={plan}/><p className="mt-5 text-3xl font-semibold text-[var(--text-primary)]">{offer ? formatMinorAmount(offer.unitAmount, offer.currency) : "Unavailable"}<span className="text-sm font-normal text-[var(--text-secondary)]"> / {interval === "year" ? "year" : "month"}</span></p>{interval === "year" && annual ? <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">Save {annual.annualDiscountPercent}% · {formatMinorAmount(annual.effectiveMonthlyAnnualRate, annual.currency)}/month effective</p> : null}<FeatureList items={plan === "plus" ? PLUS : PREMIUM}/><button type="button" disabled={disabled || pending} onClick={() => onAction(plan, offer, managed)} className="mt-7 min-h-11 w-full rounded-lg bg-brand px-4 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-55">{pending ? "Opening..." : label}</button>{!purchasable && !current && !managed ? <p className="mt-2 text-center text-xs text-[var(--text-secondary)]">Subscriptions launching soon</p> : null}</article>;
}

export default function PricingPageClient() {
  const params = useSearchParams(); const { user } = useAuth();
  const emphasized = normalizeIndexPlan(params.get("plan"));
  const [interval, setInterval] = useState("year"); const [catalog, setCatalog] = useState(null); const [status, setStatus] = useState(null); const [pending, setPending] = useState(null); const [error, setError] = useState("");
  useEffect(() => { getBillingCatalog().then(setCatalog).catch(() => setError("Membership pricing is temporarily unavailable.")); }, []);
  useEffect(() => { if (user) getBillingStatus().then(setStatus).catch(() => {}); else setStatus(null); }, [user]);
  const pricing = useMemo(() => ({ plus: planPricingSummary(catalog, "plus"), premium: planPricingSummary(catalog, "premium") }), [catalog]);
  async function act(plan, offer, managed) { if (pending) return; setError(""); setPending(plan); try { if (managed) { const r = await createCustomerPortalSession(); window.location.assign(r.portalUrl); return; } if (!user) { const next = `/pricing?plan=${plan}&interval=${interval}`; window.location.assign(`/login?next=${encodeURIComponent(next)}`); return; } const r = await createCheckoutSession(offer.offerKey); window.location.assign(r.checkoutUrl); } catch { setError("Unable to open membership purchasing right now."); setPending(null); } }
  useEffect(() => { if (params.get("interval") === "month" || params.get("interval") === "year") setInterval(params.get("interval")); }, [params]);
  return <main className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-6"><header className="mx-auto max-w-3xl text-center"><p className="text-sm font-semibold uppercase tracking-[.18em] text-[var(--accent)]">inDex Membership</p><h1 className="mt-3 text-4xl font-semibold text-[var(--text-primary)] sm:text-5xl">Choose the intelligence depth you need</h1><p className="mt-4 text-[var(--text-secondary)]">Start free, unlock deeper opening and market intelligence with Plus, or add advanced chase decision tools with Premium.</p></header><div className="mx-auto mt-8 flex w-fit rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1" role="group" aria-label="Billing interval"><button type="button" aria-pressed={interval === "month"} onClick={() => setInterval("month")} className={`rounded-lg px-5 py-2 text-sm font-semibold ${interval === "month" ? "bg-brand text-white" : "text-[var(--text-secondary)]"}`}>Monthly</button><button type="button" aria-pressed={interval === "year"} onClick={() => setInterval("year")} className={`rounded-lg px-5 py-2 text-sm font-semibold ${interval === "year" ? "bg-brand text-white" : "text-[var(--text-secondary)]"}`}>Annual</button></div>{error ? <p role="alert" className="mx-auto mt-5 max-w-xl text-center text-sm text-rose-300">{error}</p> : null}<section className="mt-10 grid gap-5 lg:grid-cols-3"><article data-pricing-plan="basic" className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6"><PlanBadge plan="basic"/><p className="mt-5 text-3xl font-semibold text-[var(--text-primary)]">Free</p><FeatureList items={BASIC}/><span className="mt-7 inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-[var(--border-subtle)] font-semibold text-[var(--text-secondary)]">Included</span></article><PaidCard plan="plus" summary={pricing.plus} interval={interval} emphasized={emphasized === "plus"} status={status} onAction={act} pending={pending === "plus"}/><PaidCard plan="premium" summary={pricing.premium} interval={interval} emphasized={emphasized === "premium"} status={status} onAction={act} pending={pending === "premium"}/></section></main>;
}
