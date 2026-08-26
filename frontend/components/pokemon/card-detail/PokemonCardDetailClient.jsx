"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { useAuth } from "@/components/AuthContext";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import { hasIndexPlusAccess } from "@/lib/access/indexPlanAccess.mjs";
import { getPokemonCardDetail } from "@/lib/pokemon/pokemonCardDetailClient";
import AssetMarketPanel from "./AssetMarketPanel";

const finite = (v) => v !== null && v !== undefined && Number.isFinite(Number(v)) ? Number(v) : null;
const money = (v) => finite(v) === null ? "Unavailable" : finite(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
const number = (v, d = 0) => finite(v) === null ? "Unavailable" : finite(v).toLocaleString("en-US", { maximumFractionDigits: d });
const percent = (v) => finite(v) === null ? "Unavailable" : `${(finite(v) * 100).toFixed(3).replace(/0+$/, "").replace(/\.$/, "")}%`;
const dateLabel = (v) => v ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${String(v).slice(0, 10)}T00:00:00Z`)) : "Unavailable";
const score = (v) => finite(v) === null ? "Unavailable" : `${(finite(v) / 10).toFixed(1)} / 10`;

function Metric({ label, children }) {
  return <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.35)] p-4"><dt className="text-xs font-semibold uppercase tracking-[.08em] text-[var(--text-secondary)]">{label}</dt><dd className="mt-2 text-xl font-semibold tabular-nums">{children}</dd></div>;
}

function VariantSelector({ detail, onSelect, pending }) {
  if (detail.availableVariants.length < 2) return null;
  return <div><p className="text-xs font-semibold text-[var(--text-secondary)]">Printing</p><div role="radiogroup" aria-label="Card printing" className="mt-2 flex flex-wrap gap-2">{detail.availableVariants.map((v) => <button key={v.cardVariantId} type="button" role="radio" aria-checked={detail.selectedVariantId === v.cardVariantId} disabled={!v.modeled || pending} onClick={() => onSelect(v.cardVariantId)} className={`min-h-11 rounded-lg border px-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${detail.selectedVariantId === v.cardVariantId ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] text-[var(--accent)]" : "border-[var(--border-subtle)] bg-white/5 text-[var(--text-secondary)] disabled:opacity-45"}`}>{v.label}{!v.modeled ? " · Not modeled" : ""}</button>)}</div></div>;
}

function PlusLock({ title }) {
  const id = title.replace(/\s/g, "-").toLowerCase();
  return <section aria-labelledby={id} className="set-glass-surface relative overflow-hidden rounded-2xl border p-6"><div aria-hidden="true" className="grid grid-cols-3 gap-3 opacity-20 blur-sm"><span className="h-20 rounded-xl bg-white/10"/><span className="h-20 rounded-xl bg-white/10"/><span className="h-20 rounded-xl bg-white/10"/></div><div className="absolute inset-0 flex flex-col items-center justify-center bg-[rgba(2,6,23,.62)] text-center"><p className="text-xs font-bold uppercase tracking-[.14em] text-amber-300">🔒 Index Plus</p><h2 id={id} className="mt-2 text-xl font-semibold">Unlock {title}</h2><Link href="/pricing" className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-amber-300/40 bg-amber-300/10 px-4 text-sm font-semibold text-amber-200">Explore Index Plus</Link></div></section>;
}

function ProbabilityJourney({ chase }) {
  const points = [["50%", chase.packsFor50PercentChance], ["75%", chase.packsFor75PercentChance], ["90%", chase.packsFor90PercentChance], ["95%", chase.packsFor95PercentChance]];
  return <section aria-labelledby="probability-title" className="rounded-2xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.35)] p-5"><h3 id="probability-title" className="text-xl font-semibold">Probability Journey</h3><p className="mt-2 text-sm text-[var(--text-secondary)]">“1 in N” is a long-run modeled rate, not a guarantee that the card appears within N packs.</p><dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">{points.map(([label, packs]) => <Metric key={label} label={`${label} Chance`}>{number(packs)} packs</Metric>)}</dl></section>;
}

function ProductEconomics({ chase }) {
  const products = useMemo(() => Array.isArray(chase.products) ? chase.products.filter((p) => p.available) : [], [chase.products]);
  const [selectedId, setSelectedId] = useState(products[0]?.sealedProductId || null);
  const selected = products.find((p) => p.sealedProductId === selectedId) || products[0];
  if (!selected) return <p className="text-sm text-[var(--text-secondary)]">No supported sealed product is available for this simulation run.</p>;
  return <div className="space-y-4"><div><h3 className="text-xl font-semibold">Choose How You Open It</h3><div role="radiogroup" aria-label="Sealed product" className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{products.map((p) => <button key={p.sealedProductId} role="radio" aria-checked={selected.sealedProductId === p.sealedProductId} onClick={() => setSelectedId(p.sealedProductId)} className={`min-h-16 rounded-xl border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${selected.sealedProductId === p.sealedProductId ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)]" : "border-[var(--border-subtle)] bg-white/5"}`}><span className="block font-semibold">{p.productName}</span><span className="text-xs text-[var(--text-secondary)]">{number(p.packCount)} packs · {percent(p.targetProbabilityPerProduct)} chance</span></button>)}</div></div><dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Product Price">{money(selected.productPrice)}</Metric><Metric label="Expected Products">{number(selected.expectedProductsToHit, 2)}</Metric><Metric label="Gross Chase Spend">{money(selected.grossSpend)}</Metric><Metric label="Recovery-adjusted Cost">{money(selected.ripAcquisitionCost)}</Metric></dl><p className="text-xs leading-relaxed text-[var(--text-secondary)]">Recovery-adjusted figures credit incidental pulls at modeled Near Mint market value before fees, shipping, condition discounts, liquidity, or sell-through.</p></div>;
}

function CardIntelligence({ detail }) {
  const chase = detail.chase || {};
  return <section aria-labelledby="card-intelligence-title" className="set-glass-surface rounded-2xl border p-5 sm:p-6"><p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">Index Plus</p><h2 id="card-intelligence-title" className="mt-1 text-2xl font-semibold">Card Intelligence</h2>{!chase.available ? <p className="mt-4 text-sm text-[var(--text-secondary)]">Modeled Card Intelligence is not currently available for this card.</p> : <div className="mt-5 space-y-5"><dl className="grid gap-3 sm:grid-cols-3"><Metric label="Pull Odds">1 in {number(chase.impliedOddsOneInN, 2)} packs</Metric><Metric label="Expected Packs">{number(chase.expectedPacksToHit, 2)}</Metric>{finite(chase.expectedSpend) !== null ? <Metric label="Expected Spend">{money(chase.expectedSpend)}</Metric> : null}</dl><ProbabilityJourney chase={chase}/><ProductEconomics chase={chase}/></div>}</section>;
}

function CollectorIntelligence({ intelligence }) {
  const metrics = [["Card Appeal", intelligence?.cardAppeal], ["Pokémon Demand", intelligence?.pokemonDemand], ["Card Treatment", intelligence?.treatment], ["Scarcity", intelligence?.scarcity]];
  return <section aria-labelledby="collector-title" className="set-glass-surface rounded-2xl border p-5 sm:p-6"><p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">Index Plus</p><h2 id="collector-title" className="mt-1 text-2xl font-semibold">Collector Intelligence</h2><p className="mt-2 max-w-3xl text-sm text-[var(--text-secondary)]">Card Appeal is a collector-interest signal combining Pokémon demand and this card’s collectible treatment. It is not a price prediction.</p><dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{metrics.map(([label, metric]) => <Metric key={label} label={label}>{metric?.available ? score(metric.score) : label === "Pokémon Demand" ? "Not applicable" : "Unavailable"}</Metric>)}</dl></section>;
}

export default function PokemonCardDetailClient({ initialDetail }) {
  const [detail, setDetail] = useState(initialDetail);
  const [error, setError] = useState(null);
  const [pending, startTransition] = useTransition();
  const { user } = useAuth();
  const router = useRouter();
  const entitled = hasIndexPlusAccess(user?.index_plan);
  const selectedVariant = detail.availableVariants.find((v) => v.cardVariantId === detail.selectedVariantId);
  const artwork = detail.set.heroImageUrl || detail.set.logoImageUrl || detail.set.symbolImageUrl;
  const selectVariant = (variantId) => startTransition(async () => { try { setError(null); const next = await getPokemonCardDetail(detail.set.id, detail.card.id, variantId); setDetail(next); router.replace(`/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}/Cards/${encodeURIComponent(detail.card.id)}?variant=${encodeURIComponent(variantId)}`, { scroll: false }); } catch (e) { setError(e.message); } });
  return <main className="index-environment set-detail-glass-scope min-h-screen px-4 pb-12 pt-6 text-[var(--text-primary)] sm:px-6 lg:px-8"><PageArtworkAtmosphere src={artwork} dataAttribute="data-card-set-ambient-artwork"/><div className="relative mx-auto max-w-[1400px] space-y-5"><nav aria-label="Breadcrumb" className="text-sm text-[var(--text-secondary)]"><Link className="hover:text-[var(--accent)]" href={`/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}`}>{detail.set.name}</Link><span aria-hidden="true"> / </span><span>{detail.card.name}</span></nav><section className="grid items-start gap-5 md:grid-cols-[minmax(210px,34%)_minmax(0,1fr)] lg:gap-8"><div className="order-2 flex justify-center md:order-1">{detail.card.imageLargeUrl || detail.card.imageSmallUrl ? <Image src={detail.card.imageLargeUrl || detail.card.imageSmallUrl} alt={`${detail.card.name} card artwork`} width={734} height={1024} priority className="h-auto max-h-[48vh] w-auto max-w-full object-contain drop-shadow-[0_24px_40px_rgba(0,0,0,.48)] md:max-h-[680px]"/> : <div className="flex aspect-[734/1024] w-full max-w-[330px] items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-white/5 text-sm text-[var(--text-secondary)]">Card artwork unavailable</div>}</div><div className="order-1 min-w-0 space-y-4 md:order-2"><header><p className="text-xs font-bold uppercase tracking-[.14em] text-[var(--accent)]">{detail.set.name}</p><h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{detail.card.name}</h1><p className="mt-2 text-sm text-[var(--text-secondary)]">{[detail.card.rarity, detail.card.printedNumber || detail.card.cardNumber].filter(Boolean).join(" · ")}</p></header><AssetMarketPanel market={detail.market}/><VariantSelector detail={detail} onSelect={selectVariant} pending={pending}/>{error ? <p role="alert" className="text-sm text-red-300">{error}</p> : null}</div></section><section aria-labelledby="details-title" className="set-glass-surface rounded-2xl border p-5"><h2 id="details-title" className="text-lg font-semibold">Card Details</h2><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-5"><div><dt className="text-[var(--text-secondary)]">Set</dt><dd className="mt-1 font-medium">{detail.set.name}</dd></div><div><dt className="text-[var(--text-secondary)]">Card Number</dt><dd className="mt-1 font-medium">{detail.card.printedNumber || detail.card.cardNumber || "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Rarity</dt><dd className="mt-1 font-medium">{detail.card.rarity || "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Printing</dt><dd className="mt-1 font-medium">{selectedVariant?.label || "Unavailable"}</dd></div><div><dt className="text-[var(--text-secondary)]">Market Price As Of</dt><dd className="mt-1 font-medium">{dateLabel(detail.market.marketDate)}</dd></div></dl></section>{entitled ? <><CardIntelligence detail={detail}/><CollectorIntelligence intelligence={detail.intelligence}/></> : <><PlusLock title="Card Intelligence"/><PlusLock title="Collector Intelligence"/></>}<details className="set-glass-surface rounded-2xl border p-5 text-sm text-[var(--text-secondary)]"><summary className="cursor-pointer font-semibold text-[var(--text-primary)]">Methodology & Provenance</summary><ul className="mt-3 grid gap-2 sm:grid-cols-2"><li>Market points are real variant and condition observations.</li><li>Pull rates and product composition are modeled, not guaranteed.</li><li>Opening outcomes are independent under the model assumptions.</li><li>Market source: {detail.market.source || "Unavailable"}; recovery model: {detail.chase?.recoveryModel || "Unavailable"}.</li></ul></details></div></main>;
}
