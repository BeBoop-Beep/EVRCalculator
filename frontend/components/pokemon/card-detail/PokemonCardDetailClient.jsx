"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { getPokemonCardDetail } from "@/lib/pokemon/pokemonCardDetailClient";

const money = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" }) : "Unavailable";
const number = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("en-US", { maximumFractionDigits: digits }) : "â€”";
const percent = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")}%` : "â€”";

function VariantSelector({ detail, onSelect, pending }) {
  if (detail.availableVariants.length < 2) return null;
  return (
    <section aria-labelledby="printing-title" className="space-y-3">
      <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-300">Printing</p><h2 id="printing-title" className="text-xl font-semibold">Choose a printing</h2></div>
      <div role="radiogroup" aria-label="Card printing" className="flex flex-wrap gap-2">
        {detail.availableVariants.map((variant) => (
          <button key={variant.cardVariantId} type="button" role="radio"
            aria-checked={detail.selectedVariantId === variant.cardVariantId}
            disabled={!variant.modeled || pending} onClick={() => onSelect(variant.cardVariantId)}
            className={`min-h-11 rounded-full border px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-300 ${detail.selectedVariantId === variant.cardVariantId ? "border-teal-300 bg-teal-300/15 text-teal-100" : "border-white/15 bg-white/5 text-slate-200 hover:border-white/30 disabled:opacity-45"}`}>
            {variant.label}{!variant.modeled ? " (not modeled)" : ""}
          </button>
        ))}
      </div>
    </section>
  );
}

function ProbabilityJourney({ chase }) {
  const milestones = [
    ["50%", chase.packsFor50PercentChance], ["75%", chase.packsFor75PercentChance],
    ["90%", chase.packsFor90PercentChance], ["95%", chase.packsFor95PercentChance],
  ];
  const max = Number(chase.packsFor95PercentChance) || 1;
  const p = Number(chase.modeledProbability) || 0;
  const points = Array.from({ length: 41 }, (_, index) => {
    const packs = max * index / 40;
    const probability = 1 - Math.pow(1 - p, packs);
    return `${(index / 40) * 100},${100 - probability * 92}`;
  }).join(" ");
  return (
    <section aria-labelledby="journey-title" className="rounded-2xl border border-white/10 bg-slate-950/55 p-5 sm:p-6">
      <h2 id="journey-title" className="text-2xl font-semibold">Probability journey</h2>
      <p className="mt-2 max-w-3xl text-sm text-slate-300">â€œ1 in Nâ€ is a long-run average, not a guarantee that the card appears within N packs.</p>
      <svg viewBox="0 0 100 100" className="mt-5 h-44 w-full overflow-visible" role="img" aria-label={`Cumulative modeled probability reaches 50 percent at ${chase.packsFor50PercentChance} packs and 95 percent at ${chase.packsFor95PercentChance} packs.`} preserveAspectRatio="none">
        <line x1="0" y1="96" x2="100" y2="96" stroke="rgba(148,163,184,.35)" />
        <polyline points={points} fill="none" stroke="rgb(45 212 191)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {milestones.map(([label, packs]) => { const x = Math.min(100, Number(packs) / max * 100); const y = 100 - Number(label.slice(0, -1)) * .92; return <g key={label}><circle cx={x} cy={y} r="1.8" fill="rgb(94 234 212)" /><title>{label} at {packs} packs</title></g>; })}
      </svg>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{milestones.map(([label, packs]) => <div key={label} className="rounded-xl bg-white/5 p-3"><p className="text-xs text-slate-400">{label} chance</p><p className="mt-1 font-semibold">{number(packs)} packs</p></div>)}</div>
    </section>
  );
}

function ProductEconomics({ chase }) {
  const products = useMemo(
    () => Array.isArray(chase.products) ? chase.products.filter((product) => product.available) : [],
    [chase.products]
  );
  const [selectedId, setSelectedId] = useState(products[0]?.sealedProductId || null);
  const selected = useMemo(() => products.find((product) => product.sealedProductId === selectedId) || products[0], [products, selectedId]);
  if (!selected) return <p className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">No supported sealed product is available for this run.</p>;
  const ratio = Number(chase.currentTargetMarketPrice) > 0 && Number(selected.ripAcquisitionCost) >= 0 ? Number(selected.ripAcquisitionCost) / Number(chase.currentTargetMarketPrice) : null;
  return (
    <div className="space-y-6">
      <section aria-labelledby="products-title"><h2 id="products-title" className="text-2xl font-semibold">Choose how youâ€™d open it</h2>
        <div role="radiogroup" aria-label="Sealed product" className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{products.map((product) => <button key={product.sealedProductId} role="radio" aria-checked={selected.sealedProductId === product.sealedProductId} onClick={() => setSelectedId(product.sealedProductId)} className={`min-h-14 rounded-xl border p-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-300 ${selected.sealedProductId === product.sealedProductId ? "border-teal-300 bg-teal-300/10" : "border-white/10 bg-white/5"}`}><span className="block font-semibold">{product.productName}</span><span className="text-xs text-slate-400">{percent(product.targetProbabilityPerProduct)} per product Â· {number(product.packCount)} packs</span></button>)}</div>
      </section>
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-5"><h2 className="text-2xl font-semibold">What would you spend?</h2>
          <dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between gap-4"><dt>Gross Chase spend</dt><dd>{money(selected.grossSpend)}</dd></div><div className="flex justify-between gap-4"><dt>Gross modeled incidental card value</dt><dd>âˆ’ {money(selected.incidentalRecovery)}</dd></div><div className="flex justify-between gap-4 border-t border-white/10 pt-3 font-semibold"><dt>Gross recovery-adjusted Chase cost</dt><dd>{money(selected.ripAcquisitionCost)}</dd></div></dl>
          <p className="mt-4 text-xs leading-relaxed text-slate-400">Gross market-value recovery assumes incidental pulls retain 100% of modeled Near Mint market value. It is not realizable cash and includes no fees, shipping, liquidity, condition, or sell-through haircut.</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-5"><h2 className="text-2xl font-semibold">Opening vs buying</h2><dl className="mt-4 space-y-3"><div><dt className="text-xs text-slate-400">Current single price</dt><dd className="text-xl font-semibold">{money(chase.currentTargetMarketPrice)}</dd></div><div><dt className="text-xs text-slate-400">Recovery-adjusted Chase cost</dt><dd className="text-xl font-semibold">{money(selected.ripAcquisitionCost)}</dd></div><div><dt className="text-xs text-slate-400">Opening / buying ratio</dt><dd className="text-3xl font-bold text-teal-200">{ratio == null ? "Unavailable" : `${number(ratio, 2)}Ã—`}</dd></div></dl><p className="mt-4 text-xs text-slate-400">A modeled comparison, not buying, selling, or investment advice.</p></div>
      </section>
    </div>
  );
}

export default function PokemonCardDetailClient({ initialDetail }) {
  const [detail, setDetail] = useState(initialDetail);
  const [error, setError] = useState(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const selectVariant = (variantId) => startTransition(async () => {
    setError(null);
    try {
      const next = await getPokemonCardDetail(detail.set.id, detail.card.id, variantId);
      setDetail(next);
      router.replace(`/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}/Cards/${encodeURIComponent(detail.card.id)}?variant=${encodeURIComponent(variantId)}`, { scroll: false });
    } catch (requestError) { setError(requestError.message); }
  });
  const chase = detail.chase || {};
  const selectedVariant = detail.availableVariants.find((variant) => variant.cardVariantId === detail.selectedVariantId);
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(13,148,136,.16),transparent_35%),#050914] px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <nav aria-label="Breadcrumb" className="text-sm text-slate-400"><Link className="rounded hover:text-teal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-300" href={`/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}`}>{detail.set.name}</Link><span aria-hidden="true"> / </span><span>{detail.card.name}</span></nav>
        <section className="grid items-start gap-7 md:grid-cols-[minmax(220px,340px)_1fr]">
          {detail.card.imageLargeUrl || detail.card.imageSmallUrl ? (
            <Image src={detail.card.imageLargeUrl || detail.card.imageSmallUrl} alt={`${detail.card.name} card artwork`} width={734} height={1024} priority className="mx-auto max-h-[58vh] h-auto w-auto max-w-full rounded-2xl object-contain drop-shadow-2xl md:max-h-none" />
          ) : (
            <div className="mx-auto flex aspect-[3/4] w-full max-w-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm text-slate-400">Card artwork unavailable</div>
          )}
          <div className="space-y-6"><div><p className="text-sm font-semibold text-teal-300">{detail.set.name}</p><h1 className="mt-1 text-4xl font-bold tracking-tight sm:text-5xl">{detail.card.name}</h1><p className="mt-2 text-slate-300">{[detail.card.printedNumber || detail.card.cardNumber, detail.card.rarity, detail.card.subtypes?.join(" / ")].filter(Boolean).join(" Â· ")}</p></div>
            <VariantSelector detail={detail} onSelect={selectVariant} pending={pending} />
            {error ? <p role="alert" className="text-sm text-red-300">{error}</p> : null}
            <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-slate-400">Selected printing</p><p className="mt-1 font-semibold">{selectedVariant?.label || (detail.variantSelection.state === "selection_required" ? "Choose a printing" : "Unavailable")}</p></div><div className="rounded-xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-slate-400">Current market price</p><p className="mt-1 text-xl font-semibold">{money(detail.market.currentPrice)}</p></div><div className="rounded-xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-slate-400">Price observed</p><p className="mt-1 font-semibold">{detail.market.marketDate || "Unavailable"}</p></div></div>
            {chase.available ? <div className="rounded-2xl border border-teal-300/25 bg-teal-300/10 p-5"><p className="text-xs font-semibold uppercase tracking-[.18em] text-teal-300">How rare is it?</p><div className="mt-2 flex flex-wrap items-end gap-x-8 gap-y-2"><p className="text-4xl font-bold">1 in {number(chase.impliedOddsOneInN, 2)}</p><p className="pb-1 text-slate-200">{percent(chase.modeledProbability)} per modeled pack</p></div><p className="mt-2 text-sm text-slate-300">Expected packs to hit (long-run average): {number(chase.expectedPacksToHit, 2)}</p></div> : null}
          </div>
        </section>
        {detail.variantSelection.state === "selection_required" ? <section className="rounded-2xl border border-amber-300/25 bg-amber-300/5 p-6"><h2 className="text-xl font-semibold">Choose a printing to see Chase economics</h2><p className="mt-2 text-sm text-slate-300">This canonical card has multiple modeled variants with different pull rates. No printing has been selected arbitrarily.</p></section> : null}
        {detail.variantSelection.state === "unavailable" || (!chase.available && detail.variantSelection.state !== "selection_required") ? <section className="rounded-2xl border border-white/10 bg-white/5 p-6"><h2 className="text-xl font-semibold">Modeled Chase data is unavailable for this card.</h2><p className="mt-2 text-sm text-slate-300">Card identity and available market information remain shown above.</p></section> : null}
        {chase.available ? <><ProbabilityJourney chase={chase} /><ProductEconomics chase={chase} /><section className="rounded-2xl border border-white/10 bg-white/5 p-5"><h2 className="text-xl font-semibold">Model assumptions & disclosures</h2><ul className="mt-3 grid gap-2 text-sm text-slate-300 sm:grid-cols-2"><li>Pull rates and product composition are modeled, not guaranteed.</li><li>Opening outcomes remain random and independent under the model.</li><li>Card and sealed-product prices use the displayed current provenance clocks.</li><li>Recovery model: <code>gross_market_value</code>; no liquidation haircut.</li></ul></section></> : null}
      </div>
    </main>
  );
}
