"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { resolveLooseBoosterPackArtwork } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";

export function RankedProductHeader({ children, text = null, info = null }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      {children}
      <InfoPopover text={text}>{info}</InfoPopover>
    </span>
  );
}

export function PremiumMetricLock() {
  return <span aria-label="Index Plus metric locked" className="inline-flex min-h-7 min-w-7 items-center justify-center rounded-md border border-[rgba(45,212,191,0.22)] bg-[rgba(45,212,191,0.05)] text-xs text-[var(--text-secondary)]">🔒</span>;
}

export function RankedProductIdentity({ product, secondary, children = null }) {
  const artwork = product?.productFamily === "loose_booster_pack"
    ? resolveLooseBoosterPackArtwork({ productImageUrl: product.productImageUrl, setCanonicalKey: product.setCanonicalKey })
    : null;
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      {artwork ? <span data-ranked-product-artwork className="flex h-[42px] w-9 flex-none items-center justify-center md:h-[52px] md:w-10"><img src={artwork.src} alt="" className="h-full w-auto max-w-full scale-[1.25] object-contain" loading="lazy" /></span> : null}
      <span className="min-w-0">
        <span className="block truncate font-semibold text-[var(--text-primary)]">{product?.productName}</span>
        {secondary ? <span className="block truncate text-xs text-[var(--text-secondary)]">{secondary}</span> : null}
        {children}
      </span>
    </span>
  );
}
