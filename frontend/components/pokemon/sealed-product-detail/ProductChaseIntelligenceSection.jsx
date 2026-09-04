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

import { useEffect, useState } from "react";
import { PlanBadge, PlanUpgradeLink } from "@/components/membership/PlanLock";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import { INDEX_PLAN_PREMIUM } from "@/lib/access/indexPlanAccess.mjs";
import InfoPopover from "@/components/ui/InfoPopover";

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
    <section className={`relative rounded-2xl border p-6 ${presentation.panelClassName}`}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Product Chase Intelligence</h3>
        <PlanBadge plan={INDEX_PLAN_PREMIUM} />
      </div>
      <p className="mt-2 text-sm opacity-80 min-h-11">
        See how much of this set&apos;s important collectible value becomes
        reachable through this product at a budget you choose.
      </p>
      <PlanUpgradeLink plan={INDEX_PLAN_PREMIUM} feature="product_chase_intelligence" />
    </section>
  );
}

/**
 * `sealedProductId` + `setId` locate this product's row in the cross-format
 * Chase Access response; `budget` is optional (Phase 10 - no budget selected
 * means no O_budget is invented, only set-level/context fields render).
 */
export default function ProductChaseIntelligenceSection({ sealedProductId, setId, budget }) {
  const [state, setState] = useState({ status: "loading", row: null });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setState({ status: "loading", row: null });
    const params = new URLSearchParams();
    if (budget != null) params.set("budget", String(budget));
    fetch(`/api/explore/product-chase-intelligence?${params.toString()}`, {
      signal: controller.signal,
      credentials: "include",
    })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("request_failed"))))
      .then((payload) => {
        if (!active) return;
        const row = (payload.products || []).find(
          (product) => product.sealedProductId === sealedProductId && product.setId === setId,
        );
        setState({ status: row ? "ready" : "unavailable", row: row || null });
      })
      .catch(() => {
        if (active) setState({ status: "error", row: null });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [sealedProductId, setId, budget]);

  if (state.status === "loading") {
    return <section className="rounded-2xl border p-6 opacity-60">Loading Chase Intelligence…</section>;
  }
  if (state.status !== "ready" || !state.row) {
    return null;
  }

  const row = state.row;
  const hasBudgetResult = row.oBudget != null;

  return (
    <section className="rounded-2xl border p-6" data-product-chase-intelligence>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Product Chase Intelligence</h3>
        <InfoPopover>
          Chase Access is a separate measure from Overall RIP. It describes how
          reachable this set&apos;s important collectible value is through this
          product&apos;s packs - not a financial return score.
        </InfoPopover>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="opacity-60">Set Chase Accessibility</dt>
          <dd className="text-xl font-semibold">{formatPct(row.aRaw)}</dd>
        </div>
        <div>
          <dt className="opacity-60">Effective Pack Cost</dt>
          <dd className="text-xl font-semibold">{formatMoney(row.effectivePackCost)}</dd>
        </div>
        {row.ece != null && (
          <div>
            <dt className="opacity-60">Efficiency (comparable-format context only)</dt>
            <dd className="text-xl font-semibold">{row.ece.toFixed(4)}</dd>
          </div>
        )}
        {hasBudgetResult && (
          <>
            <div>
              <dt className="opacity-60">Chase Access at ${budget}</dt>
              <dd className="text-xl font-semibold">{formatPct(row.oBudget)}</dd>
            </div>
            <div>
              <dt className="opacity-60">You can open</dt>
              <dd className="text-xl font-semibold">
                {row.quantity} product{row.quantity === 1 ? "" : "s"} / {row.effectivePacks} effective packs
              </dd>
            </div>
            {row.oBudgetRank != null && (
              <div>
                <dt className="opacity-60">Chase Access rank at this budget</dt>
                <dd className="text-xl font-semibold">#{row.oBudgetRank}</dd>
              </div>
            )}
          </>
        )}
      </dl>

      {!hasBudgetResult && (
        <p className="mt-4 text-sm opacity-70">
          Choose a budget to see Chase Access - the reachable share of this
          set&apos;s value at that spend - and a cross-format ranking against
          other products.
        </p>
      )}
    </section>
  );
}
