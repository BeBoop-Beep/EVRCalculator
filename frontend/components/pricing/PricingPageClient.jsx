"use client";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthContext";
import {
  createCheckoutSession,
  getBillingCatalog,
  getBillingStatus,
  previewPlanChange,
  confirmPlanChange,
  cancelScheduledPlanChange,
} from "@/lib/billing/billingClient.mjs";
import {
  formatMinorAmount,
  planPricingSummary,
} from "@/lib/billing/billingPricing.mjs";
import {
  pendingChangeCopy,
  upgradeConfirmationCopy,
  downgradeConfirmationCopy,
} from "@/lib/billing/billingPresentation.mjs";
import { normalizeIndexPlan } from "@/lib/access/indexPlanAccess.mjs";
import { PlanBadge } from "@/components/membership/PlanLock";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { resolvePaidCardMode } from "./resolvePaidCardMode.mjs";
import { resolveConfirmOutcome } from "./resolveConfirmOutcome.mjs";

export { resolvePaidCardMode, resolveConfirmOutcome };

const BASIC = [
  "Public rankings and market pulse",
  "Set and card discovery",
  "Portfolio and collection tools",
];
const PLUS = [
  "Product RIP rankings",
  "Detailed EV, recovery, and opening economics",
  "Set pack economics",
  "Era pack economics",
  "Market breadth",
  "Card pull odds",
  "Acquisition milestones",
  "Prepared Market Explorer intelligence",
  "Single-axis custom markets",
];
const PREMIUM = [
  "Everything in Index Plus",
  "Chase Efficiency ranking",
  "Best chase opening route",
  "Chase-vs-buy economics",
  "Global, era, set, and rarity chase rankings",
  "Multi-axis compound markets",
  "Pokémon-specific market construction",
  "Custom ranked market composition",
];

function FeatureList({ items }) {
  return (
    <ul className="mt-6 space-y-3 text-sm text-[var(--text-secondary)]">
      {items.map((item) => (
        <li key={item} className="flex gap-2">
          <span aria-hidden="true" className="text-[var(--accent)]">
            ✓
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function PlanChangePaymentIssueNotice({ paymentIssue, onDismiss }) {
  const message =
    paymentIssue === "requires_action"
      ? "Your bank needs to verify this payment before it can go through."
      : "This payment could not be completed.";
  return (
    <div className="mt-3 rounded-lg border border-rose-400/40 bg-rose-500/10 p-3">
      <p className="text-sm font-semibold text-rose-200">{message}</p>
      <p className="mt-1 text-sm text-rose-100/90">
        Update your payment method from your account&apos;s Manage Billing
        section, then try again.
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className="mt-3 min-h-11 w-full rounded-lg border border-[var(--border-subtle)] px-4 font-semibold text-[var(--text-secondary)]"
      >
        Dismiss
      </button>
    </div>
  );
}

function PlanChangeConfirmPanel({
  mode,
  preview,
  onConfirm,
  onDismiss,
  pending,
  paymentIssue,
  onDismissPaymentIssue,
}) {
  if (paymentIssue) {
    return (
      <PlanChangePaymentIssueNotice
        paymentIssue={paymentIssue}
        onDismiss={onDismissPaymentIssue}
      />
    );
  }
  if (!preview) return null;
  if (mode === "upgrade") {
    const copy = upgradeConfirmationCopy({
      amountDueNow: preview.amountDueNow,
      currency: preview.currency,
      nextRenewalAt: preview.nextRenewalAt,
    });
    return (
      <div
        className={`mt-4 rounded-xl border p-4 ${planPresentation("premium").panelClassName}`}
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Upgrade to Index Premium
        </h3>
        <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
          Due now: {copy.dueNowLabel}
        </p>
        {copy.bodyLines.map((line) => (
          <p key={line} className="mt-1 text-sm text-[var(--text-secondary)]">
            {line}
          </p>
        ))}
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={`min-h-11 flex-1 rounded-lg px-4 font-semibold disabled:cursor-not-allowed disabled:opacity-55 ${planPresentation("premium").ctaClassName}`}
          >
            Confirm upgrade
          </button>
          <button
            type="button"
            onClick={onDismiss}
            disabled={pending}
            className="min-h-11 flex-1 rounded-lg border border-[var(--border-subtle)] px-4 font-semibold text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-55"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }
  const copy = downgradeConfirmationCopy({ currentPlanUntil: preview.currentPlanUntil });
  return (
    <div
      className={`mt-4 rounded-xl border p-4 ${planPresentation("plus").panelClassName}`}
    >
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
        Change to Index Plus
      </h3>
      {copy.bodyLines.map((line) => (
        <p key={line} className="mt-1 text-sm text-[var(--text-secondary)]">
          {line}
        </p>
      ))}
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={pending}
          className={`min-h-11 flex-1 rounded-lg px-4 font-semibold disabled:cursor-not-allowed disabled:opacity-55 ${planPresentation("plus").ctaClassName}`}
        >
          Confirm change
        </button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={pending}
          className="min-h-11 flex-1 rounded-lg border border-[var(--border-subtle)] px-4 font-semibold text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-55"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function PaidCard({
  plan,
  summary,
  interval,
  emphasized,
  status,
  onAction,
  pending,
  preview,
  onConfirmPlanChange,
  onDismissPlanChange,
  confirmPending,
  paymentIssue,
  onDismissPaymentIssue,
}) {
  const offer = interval === "year" ? summary.annual : summary.monthly;
  const annual = summary.annualSummary;
  const managed = Boolean(status?.billingManaged);
  const purchasable = Boolean(offer?.purchasable);
  const mode = resolvePaidCardMode(plan, status);
  let label = "Coming Soon";
  let disabled = true;
  if (mode === "current") {
    label = "Current Plan";
  } else if (mode === "upgrade") {
    label = `Upgrade to Index ${plan === "premium" ? "Premium" : "Plus"}`;
    disabled = false;
  } else if (mode === "downgrade") {
    label = "Change to Index Plus";
    disabled = false;
  } else if (mode === "pending-downgrade") {
    label = "Keep Index Premium";
    disabled = false;
  } else if (mode === "checkout") {
    label = purchasable
      ? (status
          ? `Upgrade to Index ${plan === "premium" ? "Premium" : "Plus"}`
          : `Get Index ${plan === "premium" ? "Premium" : "Plus"}`)
      : "Coming Soon";
    disabled = !purchasable;
  }
  return (
    <article
      data-pricing-plan={plan}
      data-pricing-emphasized={emphasized ? "true" : "false"}
      className={`rounded-2xl border p-6 ${planPresentation(plan).panelClassName} ${emphasized ? "ring-2 ring-offset-2 ring-offset-[var(--surface-page)] " + (plan === "plus" ? "ring-amber-300/60" : "ring-violet-400/60") : ""}`}
    >
      <PlanBadge plan={plan} />
      <p className="mt-5 text-3xl font-semibold text-[var(--text-primary)]">
        {offer
          ? formatMinorAmount(offer.unitAmount, offer.currency)
          : "Unavailable"}
        <span className="text-sm font-normal text-[var(--text-secondary)]">
          {" "}
          / {interval === "year" ? "year" : "month"}
        </span>
      </p>
      {interval === "year" && annual ? (
        <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
          Save {annual.annualDiscountPercent}% ·{" "}
          {formatMinorAmount(
            annual.effectiveMonthlyAnnualRate,
            annual.currency,
          )}
          /month effective
        </p>
      ) : null}
      <FeatureList items={plan === "plus" ? PLUS : PREMIUM} />
      {mode === "pending-downgrade" && (
        <p className="mt-4 text-sm font-semibold text-[var(--text-secondary)]">
          {pendingChangeCopy(status)}
        </p>
      )}
      <button
        type="button"
        disabled={disabled || pending}
        onClick={() => onAction(plan, offer, mode)}
        className="mt-7 min-h-11 w-full rounded-lg bg-brand px-4 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-55"
      >
        {pending ? "Opening..." : label}
      </button>
      {!purchasable && mode !== "current" && !managed ? (
        <p className="mt-2 text-center text-xs text-[var(--text-secondary)]">
          Subscriptions launching soon
        </p>
      ) : null}
      {(mode === "upgrade" || mode === "downgrade") && (
        <PlanChangeConfirmPanel
          mode={mode}
          preview={preview}
          onConfirm={onConfirmPlanChange}
          onDismiss={onDismissPlanChange}
          pending={confirmPending}
          paymentIssue={paymentIssue}
          onDismissPaymentIssue={onDismissPaymentIssue}
        />
      )}
    </article>
  );
}

export default function PricingPageClient() {
  const params = useSearchParams();
  const { user } = useAuth();
  const emphasized = normalizeIndexPlan(params.get("plan"));
  const [interval, setInterval] = useState("year");
  const [catalog, setCatalog] = useState(null);
  const [status, setStatus] = useState(null);
  const [pending, setPending] = useState(null);
  const [error, setError] = useState("");
  const [planChangePreview, setPlanChangePreview] = useState(null);
  const [confirmPending, setConfirmPending] = useState(false);
  const [paymentIssue, setPaymentIssue] = useState(null);
  useEffect(() => {
    getBillingCatalog()
      .then(setCatalog)
      .catch(() => setError("Membership pricing is temporarily unavailable."));
  }, []);
  function refreshStatus() {
    if (user)
      return getBillingStatus()
        .then(setStatus)
        .catch(() => {});
    setStatus(null);
    return Promise.resolve();
  }
  useEffect(() => {
    refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);
  const pricing = useMemo(
    () => ({
      plus: planPricingSummary(catalog, "plus"),
      premium: planPricingSummary(catalog, "premium"),
    }),
    [catalog],
  );
  async function act(plan, offer, mode) {
    if (pending) return;
    setError("");
    if (mode === "pending-downgrade") {
      setPending(plan);
      try {
        await cancelScheduledPlanChange();
        await refreshStatus();
      } catch {
        setError("Unable to update your scheduled plan change right now.");
      } finally {
        setPending(null);
      }
      return;
    }
    if (mode === "upgrade" || mode === "downgrade") {
      setPending(plan);
      try {
        const preview = await previewPlanChange(offer.offerKey);
        setPlanChangePreview({ plan, mode, offerKey: offer.offerKey, ...preview });
      } catch {
        setError("Unable to preview this plan change right now.");
      } finally {
        setPending(null);
      }
      return;
    }
    setPending(plan);
    try {
      if (mode === "current") {
        return;
      }
      if (!user) {
        const next = `/pricing?plan=${plan}&interval=${interval}`;
        window.location.assign(`/login?next=${encodeURIComponent(next)}`);
        return;
      }
      const r = await createCheckoutSession(offer.offerKey);
      window.location.assign(r.checkoutUrl);
    } catch {
      setError("Unable to open membership purchasing right now.");
      setPending(null);
    }
  }
  async function confirmPlanChangeAction() {
    if (!planChangePreview || confirmPending) return;
    setConfirmPending(true);
    setError("");
    try {
      const result = await confirmPlanChange(planChangePreview.offerKey, planChangePreview.previewToken);
      const outcome = resolveConfirmOutcome(result);
      if (outcome.status === "success") {
        setPlanChangePreview(null);
        setPaymentIssue(null);
        await refreshStatus();
      } else {
        // Payment did not succeed: Premium must never be treated as
        // granted here. Keep the preview's plan association (for card
        // targeting) but swap the confirm panel for a payment-issue notice
        // directing the user to Manage Billing instead of silently closing.
        setPaymentIssue(outcome.status);
      }
    } catch {
      setError("Unable to confirm this plan change right now.");
    } finally {
      setConfirmPending(false);
    }
  }
  function dismissPlanChangePreview() {
    if (confirmPending) return;
    setPlanChangePreview(null);
    setPaymentIssue(null);
  }
  useEffect(() => {
    if (params.get("interval") === "month" || params.get("interval") === "year")
      setInterval(params.get("interval"));
  }, [params]);
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-6">
      <header className="mx-auto max-w-3xl text-center">
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-[var(--accent)]">
          inDex Membership
        </p>
        <h1 className="mt-3 text-4xl font-semibold text-[var(--text-primary)] sm:text-5xl">
          Choose the intelligence depth you need
        </h1>
        <p className="mt-4 text-[var(--text-secondary)]">
          Start free, unlock deeper opening and market intelligence with Plus,
          or add advanced chase decision tools with Premium.
        </p>
      </header>
      <div
        className="mx-auto mt-8 flex w-fit rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1"
        role="group"
        aria-label="Billing interval"
      >
        <button
          type="button"
          aria-pressed={interval === "month"}
          onClick={() => setInterval("month")}
          className={`rounded-lg px-5 py-2 text-sm font-semibold ${interval === "month" ? "bg-brand text-white" : "text-[var(--text-secondary)]"}`}
        >
          Monthly
        </button>
        <button
          type="button"
          aria-pressed={interval === "year"}
          onClick={() => setInterval("year")}
          className={`rounded-lg px-5 py-2 text-sm font-semibold ${interval === "year" ? "bg-brand text-white" : "text-[var(--text-secondary)]"}`}
        >
          Annual
        </button>
      </div>
      {error ? (
        <p
          role="alert"
          className="mx-auto mt-5 max-w-xl text-center text-sm text-rose-300"
        >
          {error}
        </p>
      ) : null}
      <section className="mt-10 grid gap-5 lg:grid-cols-3">
        <article
          data-pricing-plan="basic"
          className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6"
        >
          <PlanBadge plan="basic" />
          <p className="mt-5 text-3xl font-semibold text-[var(--text-primary)]">
            Free
          </p>
          <FeatureList items={BASIC} />
          <span className="mt-7 inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-[var(--border-subtle)] font-semibold text-[var(--text-secondary)]">
            Included
          </span>
        </article>
        <PaidCard
          plan="plus"
          summary={pricing.plus}
          interval={interval}
          emphasized={emphasized === "plus"}
          status={status}
          onAction={act}
          pending={pending === "plus"}
          preview={planChangePreview?.plan === "plus" ? planChangePreview : null}
          onConfirmPlanChange={confirmPlanChangeAction}
          onDismissPlanChange={dismissPlanChangePreview}
          confirmPending={confirmPending}
          paymentIssue={planChangePreview?.plan === "plus" ? paymentIssue : null}
          onDismissPaymentIssue={dismissPlanChangePreview}
        />
        <PaidCard
          plan="premium"
          summary={pricing.premium}
          interval={interval}
          emphasized={emphasized === "premium"}
          status={status}
          onAction={act}
          pending={pending === "premium"}
          preview={planChangePreview?.plan === "premium" ? planChangePreview : null}
          onConfirmPlanChange={confirmPlanChangeAction}
          onDismissPlanChange={dismissPlanChangePreview}
          confirmPending={confirmPending}
          paymentIssue={planChangePreview?.plan === "premium" ? paymentIssue : null}
          onDismissPaymentIssue={dismissPlanChangePreview}
        />
      </section>
    </main>
  );
}
