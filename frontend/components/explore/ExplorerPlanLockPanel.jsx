"use client";

import Link from "next/link";
import { INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM } from "@/lib/access/indexPlanAccess.mjs";

// ---------------------------------------------------------------------------
// The locked state for one Explorer group.
//
// WHAT IT DELIBERATELY DOES AND DOES NOT DO. It shows that deeper research
// EXISTS without giving the result away: a sentence naming the capability and
// one action. It never renders the gated controls underneath in a disabled
// state — a disabled list of every published rarity would leak the taxonomy the
// gate is there to sell.
//
// LOGIN IS NOT THE UNLOCK. Copy here never says "Sign in to unlock", because
// signing in grants nothing: an authenticated account with no paid plan has the
// same feature access as an anonymous visitor. What it says depends on the two
// facts that actually matter — which PLAN is required, and whether the visitor
// has an account yet — so the action offered is the real next step:
//
//   anonymous          -> create/sign in to an account first, then upgrade.
//   authenticated basic-> the Index Plus upgrade path.
//   Index Plus         -> the Index Premium upgrade path (Build a Market only).
//
// THERE IS NO PLAN-PURCHASE ROUTE IN THIS APPLICATION YET. `/login` exists;
// nothing that sells or manages an Index plan does. So the upgrade action is
// rendered as STATED COPY rather than a link: shipping a button that 404s is
// worse than a locked panel that plainly names the plan it needs. When the
// plan surface lands, set INDEX_PLAN_UPGRADE_HREF and the button appears —
// that is the only change this file needs.
// ---------------------------------------------------------------------------

/**
 * Where the plan pages live. One place, so copy cannot drift from routing.
 *
 * `null` means "no such route exists yet"; every consumer renders copy instead
 * of a dead link. It is deliberately not a guess at a future path.
 */
export const INDEX_PLAN_UPGRADE_HREF = null;
export const SIGN_IN_HREF = "/login";

const PLAN_LABEL = {
  [INDEX_PLAN_PLUS]: "Index Plus",
  [INDEX_PLAN_PREMIUM]: "Index Premium",
};

export function describePlanLock({ requiredPlan, isAuthenticated, currentPlan = null }) {
  const planLabel = PLAN_LABEL[requiredPlan] || "a paid plan";
  if (!isAuthenticated) {
    return {
      headline: `Available with ${planLabel}`,
      actionLabel: "Sign in",
      actionHref: SIGN_IN_HREF,
      // Said explicitly, because "Sign in" next to a locked feature otherwise
      // reads as a promise that signing in is enough.
      footnote: `Requires an account on ${planLabel}.`,
    };
  }
  if (requiredPlan === INDEX_PLAN_PREMIUM && currentPlan === INDEX_PLAN_PLUS) {
    return {
      headline: "Available with Index Premium",
      actionLabel: "Upgrade to Index Premium",
      actionHref: INDEX_PLAN_UPGRADE_HREF,
      footnote: "You have Index Plus. Index Premium adds custom market building.",
    };
  }
  return {
    headline: `Available with ${planLabel}`,
    actionLabel: `Upgrade to ${planLabel}`,
    actionHref: INDEX_PLAN_UPGRADE_HREF,
    footnote: null,
  };
}

const actionClassName = [
  "mt-2 inline-flex min-h-9 items-center rounded-md border border-[rgb(45,212,191)]",
  "bg-[rgba(45,212,191,0.14)] px-2.5 text-[11px] font-semibold text-[rgb(45,212,191)]",
].join(" ");

export default function ExplorerPlanLockPanel({
  requiredPlan,
  isAuthenticated = false,
  currentPlan = null,
  /** What the group actually does. One sentence, specific to the group. */
  description,
}) {
  const lock = describePlanLock({ requiredPlan, isAuthenticated, currentPlan });
  return (
    <div
      data-explorer-plan-lock={requiredPlan}
      data-explorer-plan-lock-authenticated={isAuthenticated ? "true" : "false"}
      className="mt-1 min-w-0 rounded-md border border-[rgba(45,212,191,0.22)] bg-[rgba(45,212,191,0.05)] px-2.5 py-2.5"
    >
      <p data-explorer-plan-lock-headline className="text-[11px] font-semibold text-[var(--text-primary)]">
        {lock.headline}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{description}</p>
      {lock.actionHref ? (
        <Link
          href={lock.actionHref}
          data-explorer-plan-lock-action
          className={`${actionClassName} transition-colors hover:bg-[rgba(45,212,191,0.22)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]`}
        >
          {lock.actionLabel}
        </Link>
      ) : (
        // No plan-purchase route exists yet. Stated, not linked — a button
        // that 404s is a worse experience than none, and a fabricated href
        // would be a promise this application cannot keep.
        <span
          data-explorer-plan-lock-action
          data-explorer-plan-lock-action-pending="true"
          className={actionClassName}
        >
          {lock.actionLabel}
        </span>
      )}
      {lock.footnote ? (
        <p data-explorer-plan-lock-footnote className="mt-1.5 text-[10px] text-[var(--text-secondary)]">
          {lock.footnote}
        </p>
      ) : null}
    </div>
  );
}
