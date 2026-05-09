"use client";

import Link from "next/link";

import {
  CardDetailMarketHistorySection,
  CardDetailMarketProvider,
  CardDetailSelectedPriceCard,
} from "@/components/cards/CardDetailMarketClient";

export default function CardDetailPageClient({ payload }) {
  const identity = payload?.identity || {};
  const images = payload?.images || {};
  const setInfo = payload?.set || {};
  const conditionPrices = Array.isArray(payload?.condition_prices) ? payload.condition_prices : [];
  const gradedPrices = Array.isArray(payload?.graded_prices) ? payload.graded_prices : [];
  const priceHistory = payload?.price_history || { raw: [], graded: [] };
  const variantOptions = Array.isArray(payload?.variant_options) ? payload.variant_options : [];
  const userInventoryState = payload?.user_inventory_state || {
    is_authenticated: false,
    card_holdings: [],
    graded_holdings: [],
  };

  const imageSrc = images.image_large_url || images.image_small_url || null;
  const hasCardHoldings = Array.isArray(userInventoryState.card_holdings) && userInventoryState.card_holdings.length > 0;
  const hasGradedHoldings = Array.isArray(userInventoryState.graded_holdings) && userInventoryState.graded_holdings.length > 0;

  const toCurrency = (value) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return "-";
    }
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(parsed);
  };

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <CardDetailMarketProvider conditionPrices={conditionPrices} gradedPrices={gradedPrices} priceHistory={priceHistory}>
        <section className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(18,26,44,0.92),rgba(11,16,30,0.96))] p-4 shadow-[0_14px_40px_rgba(3,8,20,0.36)]">
            <div className="mx-auto w-full max-w-[19.5rem] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[rgba(0,0,0,0.2)] p-1">
              {imageSrc ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={imageSrc}
                  alt={identity.name ? `${identity.name} card image` : "Card image"}
                  className="h-auto w-full rounded-lg object-contain"
                  loading="eager"
                />
              ) : (
                <div className="aspect-[3/4] w-full rounded-lg bg-[var(--surface-panel)]" />
              )}
            </div>

            <div className="mt-4 rounded-xl border border-[rgba(20,184,166,0.22)] bg-[var(--surface-panel)]/80 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Inventory</p>
              {!userInventoryState.is_authenticated ? (
                <div className="mt-3 space-y-3">
                  <p className="text-sm text-[var(--text-secondary)]">Sign in to manage inventory for this card.</p>
                  <Link
                    href="/login"
                    className="inline-flex items-center justify-center rounded-lg border border-brand bg-brand px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-dark hover:border-brand-dark"
                  >
                    Login To Add
                  </Link>
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  <p className="text-sm text-[var(--text-secondary)]">
                    {hasCardHoldings || hasGradedHoldings
                      ? "You own this card variant. Quantity controls will be wired in the next phase."
                      : "Add flow coming next. Creation of new holdings is not enabled in this phase."}
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    <button type="button" disabled className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] opacity-60">
                      -
                    </button>
                    <button type="button" disabled className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] opacity-60">
                      Add
                    </button>
                    <button type="button" disabled className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] opacity-60">
                      +
                    </button>
                  </div>
                </div>
              )}
            </div>
          </article>

          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(160deg,rgba(16,22,36,0.95),rgba(10,14,25,0.98))] p-5 shadow-[0_14px_40px_rgba(3,8,20,0.3)]">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Card Detail</p>
            <h1 className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{identity.name || "Unknown Card"}</h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {(setInfo.set_name || "Unknown Set")}
              {identity.card_number ? ` | #${identity.card_number}` : ""}
            </p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Rarity</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{identity.rarity || "-"}</p>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Variant</p>
                <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                  {[identity.printing_type, identity.special_type, identity.edition].filter(Boolean).join(" | ") || "-"}
                </p>
              </div>
              <CardDetailSelectedPriceCard />
            </div>

            <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Set</p>
              <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">{setInfo.set_name || "-"}</p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{[setInfo.era_name, setInfo.release_date].filter(Boolean).join(" | ") || "-"}</p>
            </div>
          </article>
        </section>

        <section>
          <CardDetailMarketHistorySection />
        </section>

        <section>
          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
            <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Variants</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {variantOptions.length === 0 ? (
                <p className="text-sm text-[var(--text-secondary)]">No sibling variants were found.</p>
              ) : (
                variantOptions.map((option) => {
                  const isCurrent = String(option.card_variant_id) === String(identity.card_variant_id);
                  return (
                    <Link
                      key={String(option.card_variant_id)}
                      href={`/cards/${encodeURIComponent(String(option.card_variant_id))}`}
                      className={`rounded-lg border px-3 py-2 text-sm transition ${
                        isCurrent
                          ? "border-brand bg-brand text-white"
                          : "border-[var(--border-subtle)] bg-[var(--surface-panel)] text-[var(--text-primary)] hover:border-brand"
                      }`}
                    >
                      {[option.printing_type, option.special_type, option.edition].filter(Boolean).join(" | ") || `Variant ${option.card_variant_id}`}
                    </Link>
                  );
                })
              )}
            </div>
          </article>
        </section>
      </CardDetailMarketProvider>
    </main>
  );
}
