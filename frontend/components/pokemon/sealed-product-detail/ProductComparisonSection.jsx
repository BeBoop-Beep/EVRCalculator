"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import { comparisonRows, finite, pluralFamilyLabel } from "./productDetailModel.mjs";

const money = (value) => finite(value) === null ? "Market unavailable" : finite(value).toLocaleString("en-US", { style: "currency", currency: "USD" });

function MiniVisual({ row }) {
  if (row.imageUrl) return <img src={row.imageUrl} alt={`${row.name} sealed product`} className="h-full w-full object-contain drop-shadow-[0_10px_18px_rgba(0,0,0,.4)]" />;
  return <div data-comparison-image-placeholder className="flex h-full w-full items-center justify-center rounded-lg border border-dashed border-[var(--border-subtle)] bg-white/[.025]"><span aria-hidden="true" className="h-10 w-7 rounded border border-white/15 bg-white/[.035] shadow-[6px_4px_0_rgba(255,255,255,.025)]" /></div>;
}

export default function ProductComparisonSection({ detail, entitled }) {
  const [mode, setMode] = useState("sameSet");
  const rows = useMemo(() => comparisonRows(detail, mode), [detail, mode]);
  const sameFormat = mode === "sameFamily";
  const title = sameFormat ? `Compare Other ${pluralFamilyLabel(detail.product.productFamilyLabel)}` : `Other Ways to Open ${detail.set.name}`;
  return (
    <section data-product-comparisons aria-labelledby="comparison-title" className="set-glass-surface rounded-2xl border p-4 sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="comparison-title" className="text-2xl font-semibold">Compare Opening Options</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">{title}</p></div><SegmentedControl options={[{ value: "sameSet", label: "This Set" }, { value: "sameFamily", label: "Same Format" }]} value={mode} onChange={setMode} ariaLabel="Comparison scope" mobileFullWidth /></div>
      {rows.length ? <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">{rows.map((row) => {
        const href = buildSealedProductHref(row);
        return <Link data-comparison-product={row.sealedProductId} key={row.sealedProductId} href={href} className="group min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[rgba(2,8,23,.38)] p-3 transition hover:border-[color-mix(in_srgb,var(--accent)_40%,transparent)] hover:bg-white/[.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"><div className="mx-auto h-24 w-full max-w-28"><MiniVisual row={row} /></div><p className="mt-3 line-clamp-2 min-h-10 text-sm font-semibold leading-5">{row.name}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{row.setName || (mode === "sameSet" ? detail.set.name : row.productFamilyLabel)}</p><p className="mt-2 text-sm font-semibold tabular-nums">{money(row.currentPrice)}</p>{entitled && row.rankable ? <div className="mt-2 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--text-secondary)]"><p><strong className="text-[var(--text-primary)]">{formatPublicRipScore(row.overallRipLeaderScore)} / 10</strong> · {row.publicTier || "—"} Tier</p><p className="mt-1">Format Rank #{row.familyRank} of {row.familySize}</p></div> : null}<span className="mt-3 inline-flex text-xs font-semibold text-[var(--accent)]">View Product <span aria-hidden="true" className="ml-1 transition-transform group-hover:translate-x-1">→</span></span></Link>;
      })}</div> : <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-7 text-center text-sm text-[var(--text-secondary)]">{sameFormat ? "No current same-format ranked comparisons are available." : "No other tracked products are available for this set."}</p>}
    </section>
  );
}
