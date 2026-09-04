"use client";

// Product Chase Intelligence (Chase Access at Budget / O_budget) - PREMIUM.
//
// This is a SEPARATE, DISTINCT construct from Overall RIP V12, from the
// normal Plus product/budget rankings, and from Card Chase Efficiency (the
// existing card-level Premium construct rendered on the card detail page).
// It must never be presented as "part of Overall RIP" - the whole point of
// the underlying research is that ECE/O_budget answer a DIFFERENT question
// ("how reachable is this set's value through this product at my budget?")
// than the financial/collector-appeal blend that Overall RIP itself scores.
//
// NO FORMULA COMPUTATION HAPPENS HERE. Every number below (Accessibility %,
// effective pack cost, ECE, O_budget, quantity, effective packs) is read
// verbatim from the PREMIUM-only `/explore/product-chase-intelligence`
// server response - this component only formats and displays it.
//
// COPY DISCIPLINE: never say "chance of pulling a chase" or "chance to hit
// the chase" - there is no discrete chase roster. O_budget is a bounded
// weighted-reachability index, not a literal event probability.

import { useEffect, useState } from "react";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { INDEX_PLAN_PREMIUM } from "@/lib/access/indexPlanAccess.mjs";
import InfoPopover from "@/components/ui/InfoPopover";

// Canonical explicit-budget bands. Mirrors the numeric bands already used by
// the Plus budget-constrained product ranking (see ALLOWED_BUDGETS in
// frontend/lib/explore/overallProductRankingsServer.js) - kept as a local
// constant here rather than importing that module, since this section never
// requests "full_market" (an unbounded/"unlimited" budget must never be
// invented as a Chase Access default - Phase 5). $100 is used as the default
// starting band: there is no defensible personalized default budget without
// a stored user preference, so a clearly-labeled, changeable canonical band
// is shown instead.
export const CANONICAL_CHASE_BUDGETS = [25, 50, 100, 150, 250, 500];
export const DEFAULT_CHASE_BUDGET = 100;

function formatPct(value) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatMoney(value) {
  return value == null ? "—" : `$${Number(value).toFixed(2)}`;
}

/** Premium-only lock shown to Free/Plus users, matching the existing
 * PlusLock/PremiumLock visual language used elsewhere on this page. */
export function ProductChaseIntelligenceLock() {
  const presentation = planPresentation(INDEX_PLAN_PREMIUM);
  return (
    <section
      data-product-chase-intelligence-lock
      className={`relative rounded-2xl border p-6 ${presentation.panelClassName}`}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Product Chase Intelligence</h3>
        <PlanBadge plan={INDEX_PLAN_PREMIUM} />
      </div>
      <p className="mt-2 text-sm opacity-80 min-h-11">
        At a budget you choose, see how much access this product gives you to
        the set&apos;s most important collectible value.
      </p>
      <PlanUpgradeLink requiredPlan={INDEX_PLAN_PREMIUM} source="sealed-product-chase-intelligence" className="mt-4" />
    </section>
  );
}

function BudgetSelector({ budget, onChange }) {
  return (
    <div data-chase-budget-selector className="mt-4 flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold uppercase tracking-[.08em] opacity-60">Budget</span>
      <div className="flex flex-wrap gap-1.5">
        {CANONICAL_CHASE_BUDGETS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={option === budget}
            onClick={() => onChange(option)}
            className={`min-h-9 rounded-lg border px-3 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
              option === budget
                ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)]"
                : "border-[var(--border-subtle)] bg-white/[.025] hover:bg-white/[.05]"
            }`}
          >
            ${option}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * `sealedProductId` + `setId` locate this product's row. `sealedProductId` is
 * always sent to the server as an explicit scope param (Phase 12): the
 * server resolves ONLY this product's set (1 Accessibility read + 1
 * variant-universe read) instead of the full multi-set cohort, so loading
 * this section on a product detail page never pays for a global ranking
 * resolution it doesn't need. Because of that scoping, no cross-product rank
 * is shown here - a real cross-format Chase Access ranking is a separate,
 * deliberately more expensive, on-demand operation (Phase 8).
 */
export default function ProductChaseIntelligenceSection({ sealedProductId, setId }) {
  const [budget, setBudget] = useState(DEFAULT_CHASE_BUDGET);
  const [state, setState] = useState({ status: "loading", row: null });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setState({ status: "loading", row: null });
    const params = new URLSearchParams();
    params.set("budget", String(budget));
    params.set("sealed_product_id", String(sealedProductId));
    fetch(`/api/explore/product-chase-intelligence?${params.toString()}`, {
      signal: controller.signal,
      credentials: "include",
    })
      .then((response) => {
        if (response.status === 404) return { products: [] };
        if (!response.ok) return Promise.reject(new Error("request_failed"));
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        const row = (payload.products || []).find(
          (product) => product.sealedProductId === sealedProductId && product.setId === setId,
        ) || (payload.products || [])[0] || null;
        setState({ status: row ? "ready" : "unavailable", row });
      })
      .catch(() => {
        if (active) setState({ status: "error", row: null });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [sealedProductId, setId, budget]);

  return (
    <section className="rounded-2xl border p-6" data-product-chase-intelligence>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Product Chase Intelligence · Index Premium</h3>
        <InfoPopover text="Chase Access is a separate measure from Overall RIP. It describes how reachable this set's most important collectible value is through this product's packs at a budget you choose - it is not a financial return score." />
      </div>
      <p className="mt-1.5 max-w-2xl text-sm text-[var(--text-secondary)]">
        At this budget, how much access does this product give you to the
        set&apos;s most important collectible value?
      </p>

      <BudgetSelector budget={budget} onChange={setBudget} />

      {state.status === "loading" && (
        <p data-chase-state="loading" className="mt-4 text-sm opacity-60">
          Loading Chase Access…
        </p>
      )}

      {state.status === "error" && (
        <p data-chase-state="error" className="mt-4 text-sm text-[var(--text-secondary)]">
          Chase Access couldn&apos;t be loaded right now. Please try again.
        </p>
      )}

      {state.status === "unavailable" && (
        <p data-chase-state="unavailable" className="mt-4 text-sm text-[var(--text-secondary)]">
          Chase Access is not currently available for this product.
        </p>
      )}

      {state.status === "ready" && state.row && (
        <ProductChaseIntelligenceContent row={state.row} budget={budget} />
      )}
    </section>
  );
}

function ProductChaseIntelligenceContent({ row, budget }) {
  if (!row.chaseAccessibilityReady) {
    return (
      <p data-chase-state="authority-unavailable" className="mt-4 text-sm text-[var(--text-secondary)]">
        Chase Accessibility is not currently ready for this product&apos;s set
        {row.chaseAccessibilityReasons?.length
          ? `: ${row.chaseAccessibilityReasons.map((r) => r.reason || r).join("; ")}.`
          : "."}
      </p>
    );
  }

  if (row.oBudgetStatus === "unavailable_budget_below_one_unit") {
    return (
      <p data-chase-state="budget-below-minimum" className="mt-4 text-sm text-[var(--text-secondary)]">
        Budget is below the current price of one unit.
      </p>
    );
  }

  if (row.oBudgetStatus && row.oBudgetStatus.startsWith("unavailable")) {
    return (
      <p data-chase-state="unsupported-composition" className="mt-4 text-sm text-[var(--text-secondary)]">
        Chase Access can&apos;t be modeled for this product&apos;s pack
        composition right now.
      </p>
    );
  }

  const hasBudgetResult = row.oBudget != null;

  return (
    <>
      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
        {hasBudgetResult && (
          <div data-chase-primary-metric className="col-span-2">
            <dt className="opacity-60">Chase Access at ${budget}</dt>
            <dd className="text-3xl font-semibold">{formatPct(row.oBudget)}</dd>
          </div>
        )}
        {hasBudgetResult && (
          <div>
            <dt className="opacity-60">Quantity at this budget</dt>
            <dd className="text-xl font-semibold">
              {row.quantity} product{row.quantity === 1 ? "" : "s"}
            </dd>
          </div>
        )}
        {hasBudgetResult && (
          <div>
            <dt className="opacity-60">Effective random packs</dt>
            <dd className="text-xl font-semibold">{row.effectivePacks}</dd>
          </div>
        )}
        {hasBudgetResult && (
          <div>
            <dt className="opacity-60">Actual committed capital</dt>
            <dd className="text-xl font-semibold">{formatMoney(row.actualCommittedCapital)}</dd>
          </div>
        )}
        {hasBudgetResult && row.unusedCapital > 0 && (
          <div>
            <dt className="opacity-60">Unused capital</dt>
            <dd className="text-xl font-semibold">{formatMoney(row.unusedCapital)}</dd>
          </div>
        )}
        <div>
          <dt className="opacity-60">Set Chase Accessibility</dt>
          <dd className="text-xl font-semibold">{formatPct(row.aRaw)}</dd>
        </div>
        <div>
          <dt className="opacity-60">Effective Pack Cost</dt>
          <dd className="text-xl font-semibold">{formatMoney(row.effectivePackCost)}</dd>
        </div>
        {row.ece != null && (
          <div className="col-span-2">
            <dt className="flex items-center gap-1.5 opacity-60">
              Effective Pack Efficiency
              <InfoPopover text="Reflects Set Chase Accessibility relative to this product's effective pack cost. It is a per-product diagnostic, not an overall product score, and carries no cross-format rank." />
            </dt>
            <dd className="text-xl font-semibold">{row.ece.toFixed(4)}</dd>
          </div>
        )}
      </dl>

      {!hasBudgetResult && (
        <p className="mt-4 text-sm opacity-70">
          Choose a budget to see Chase Access - the reachable share of this
          set&apos;s value at that spend.
        </p>
      )}
    </>
  );
}
