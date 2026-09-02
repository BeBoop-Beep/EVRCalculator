"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { optimizedImageUrl, SET_LOGO_WIDTH } from "@/lib/images/remoteImageDelivery.mjs";
import { hasIndexPlusAccess } from "@/lib/access/indexPlanAccess.mjs";
import SealedProductMarketPanel from "./SealedProductMarketPanel";
import ProductComparisonSection from "./ProductComparisonSection";
import { ProductOpeningProfile, ProductRipLock, ProductRipSection } from "./ProductRipSection";
import { formatEvRepPacks, formatEvRepPercent } from "../../explore/evRepresentativenessSelector.mjs";
import { buildProductParentSetHref, finite, selectSetEvRealizationHeadline } from "./productDetailModel.mjs";

const dateLabel = (value) => value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${String(value).slice(0, 10)}T00:00:00Z`)) : "Unavailable";

function ProductVisual({ product }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [product.imageUrl]);
  if (product.imageUrl && !failed) return <img data-product-image src={product.imageUrl} alt={`${product.name} sealed product`} onError={() => setFailed(true)} className="h-full max-h-[390px] w-full object-contain drop-shadow-[0_24px_40px_rgba(0,0,0,.5)]" />;
  return <div data-product-image-placeholder role="img" aria-label="Product image unavailable" className="flex h-full min-h-[280px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[linear-gradient(145deg,rgba(255,255,255,.04),rgba(2,8,23,.24))] px-6 text-center"><span aria-hidden="true" className="relative h-32 w-24 rounded-xl border border-white/15 bg-[linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.015))] shadow-[14px_10px_0_rgba(255,255,255,.025),0_24px_40px_rgba(0,0,0,.35)]"><span className="absolute inset-x-4 top-5 h-px bg-white/15" /><span className="absolute inset-x-5 bottom-6 h-10 rounded border border-white/10" /></span><strong className="mt-5 text-sm font-semibold">Product image unavailable</strong><span className="mt-1 text-xs text-[var(--text-secondary)]">Image coming soon</span></div>;
}

export default function SealedProductDetailClient({ initialDetail }) {
  const detail = initialDetail;
  const { user } = useAuth();
  const entitled = hasIndexPlusAccess(user?.index_plan);
  const setHref = buildProductParentSetHref(detail.set);
  const atmosphere = optimizedImageUrl(detail.set.heroImageUrl || detail.set.logoImageUrl || detail.set.symbolImageUrl, SET_LOGO_WIDTH);
  const packCount = finite(detail.rip?.composition?.packCount);
  const setEvRealization = selectSetEvRealizationHeadline(detail.rip);
  return (
    <main className="card-detail-environment index-environment set-detail-glass-scope relative isolate min-h-screen px-4 pb-10 pt-5 text-[var(--text-primary)] sm:px-6 lg:px-8">
      <PageArtworkAtmosphere src={atmosphere} dataAttribute="data-product-set-ambient-artwork" visibilityClassName="hidden sm:block" />
      <nav data-product-back-navigation className="relative mx-auto mb-4 max-w-[1600px]"><Link href={setHref} className="inline-flex min-h-10 items-center rounded-lg pr-3 text-sm font-semibold text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">← Back to {detail.set.name}</Link></nav>
      <div className="relative mx-auto max-w-[1400px] space-y-4">
        <section data-product-detail-hero className="grid gap-4 md:grid-cols-[minmax(260px,36%)_minmax(0,1fr)] md:items-stretch lg:gap-7">
          <div className="order-1 flex min-w-0 md:h-full md:min-h-0"><div className="grid h-full min-h-0 w-full gap-4 md:grid-rows-[auto_minmax(0,1fr)]">
            <header data-product-identity className="min-w-0 text-left"><p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">{detail.set.name}</p><h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{detail.product.name}</h1><p className="mt-1.5 text-sm text-[var(--text-secondary)]">{detail.product.productFamilyLabel}{packCount ? ` · ${packCount} ${packCount === 1 ? "Pack" : "Packs"}` : ""}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{detail.market.marketDate ? `Market Price As Of ${dateLabel(detail.market.marketDate)}` : "Market Price Date Unavailable"}</p>{setEvRealization ? <p data-set-ev-realization-headline className="mt-1 text-xs text-[var(--text-secondary)]">Set EV Realization: about {formatEvRepPercent(setEvRealization.openerProbability)} of modeled openers of {detail.set.name} reach at least {formatEvRepPercent(setEvRealization.targetEvRatio)} of the set&apos;s long-run EV by <strong className="text-[var(--text-primary)]">{formatEvRepPacks(setEvRealization.packCount)}</strong>.</p> : null}</header>
            <div data-product-visual-frame className="flex min-h-[280px] w-full items-center justify-center md:min-h-0 md:items-end"><ProductVisual product={detail.product} /></div>
          </div></div>
          <div className="order-2 min-w-0 md:h-full"><SealedProductMarketPanel market={detail.market} productName={detail.product.name} /></div>
        </section>
        {detail.rip.available ? entitled ? <><ProductRipSection detail={detail} /><ProductOpeningProfile rip={detail.rip} currentPrice={detail.market.currentPrice} /></> : <ProductRipLock /> : <ProductRipSection detail={detail} />}
        <ProductComparisonSection detail={detail} entitled={entitled} />
        <details className="set-glass-surface rounded-2xl border p-4 text-sm text-[var(--text-secondary)]"><summary className="cursor-pointer font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]">Methodology & Provenance</summary><ul className="mt-3 grid gap-2 sm:grid-cols-2"><li>Sealed market points are real tracked observations.</li><li>Opening outcomes are modeled, not guaranteed.</li><li>Natural-unit product rank compares only within product family.</li><li>Opening outcomes follow the current model’s independence assumptions.</li><li>Market prices are derived from tracked market observations.</li><li>Recovery uses gross market value; calculation run: {detail.rip.calculationRunId || "Unavailable"}.</li></ul></details>
        <section data-set-rip-cta className="set-glass-surface rounded-2xl border p-5 sm:flex sm:items-center sm:justify-between sm:gap-6"><div><h2 className="text-xl font-semibold">Explore {detail.set.name} RIP Statistics</h2><p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">See how the full set ranks, review its simulated opening distribution, and compare every supported opening format.</p></div><Link href={setHref} className="mt-4 inline-flex min-h-11 flex-none items-center rounded-lg border border-[color-mix(in_srgb,var(--accent)_35%,transparent)] bg-[color-mix(in_srgb,var(--accent)_10%,transparent)] px-4 text-sm font-semibold text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] sm:mt-0">View {detail.set.name} RIP Statistics <span aria-hidden="true" className="ml-1">→</span></Link></section>
      </div>
    </main>
  );
}
