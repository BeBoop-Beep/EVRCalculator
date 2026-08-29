"use client";

import OpeningEconomicsDistribution from "./OpeningEconomicsDistribution";
import { isAvailable } from "./openingEconomicsSelector.mjs";
import styles from "./explore.module.css";
import local from "./openingEconomics.module.css";

const METHODOLOGY = [
  "Every eligible modeled sealed product is normalized to an all-in per-pack equivalent.",
  "Within each set, represented product families receive equal weight and SKUs inside each family receive equal weight.",
  "Every modeled set receives equal weight globally.",
  "Typical Opening is the median of the weighted empirical product-opening distribution, not an average of product or set medians.",
  "Guaranteed modeled card components are included exactly once before normalization; accessories have zero modeled value.",
  "Card values are gross modeled market values before selling fees, shipping, grading, liquidity discounts, and taxes.",
];

function Header({ scope, marketDate }) {
  return <header className="mb-4">
    <h2 className="text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">Pokémon Opening Economics</h2>
    <p className="mt-1 text-sm text-[var(--text-secondary)]">All modeled sealed products normalized per pack.</p>
    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
      <span className="tabular-nums">{scope.setCount} modeled sets</span><span aria-hidden="true" className="opacity-40">·</span>
      <span className="tabular-nums">{scope.productFamilyCount} represented product families</span><span aria-hidden="true" className="opacity-40">·</span>
      <span className="tabular-nums">{scope.productSkuCount} modeled products</span>
      {marketDate ? <><span aria-hidden="true" className="opacity-40">·</span><span className="tabular-nums">Opening data as of {marketDate}</span></> : null}
    </div>
  </header>;
}

export function OpeningEconomicsEmpty({ economics, title, subject }) {
  const failed = economics?.reason === "request_failed" || economics?.reason === "backend_error";
  return <section className={`${styles.surface} rounded-xl p-5`} data-opening-economics-unavailable>
    <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
    <p className="mt-1.5 max-w-prose text-sm text-[var(--text-secondary)]">{failed ? `${subject} could not be loaded. The other ranking views are unaffected.` : `The current published snapshot does not yet contain aggregate ${subject.toLowerCase()}.`}</p>
  </section>;
}

export function OpeningEconomicsSkeleton() {
  return <section aria-busy="true" aria-label="Loading opening economics" data-opening-economics-skeleton>
    <div className={`${local.skeleton} h-7 w-64`} /><div className={`${local.skeleton} mt-2 h-4 w-80 max-w-full`} />
    <div className={`${styles.surface} mt-4 rounded-xl p-5`}><div className="grid grid-cols-2 gap-4 lg:grid-cols-4"><div className={`${local.skeleton} h-16`} /><div className={`${local.skeleton} h-16`} /><div className={`${local.skeleton} h-16`} /><div className={`${local.skeleton} h-16`} /></div><div className={`${local.skeleton} mt-4 h-[18rem]`} /></div>
  </section>;
}

export default function OpeningEconomicsOverall({ economics, targets = [] }) {
  if (economics?.status === "loading") return <OpeningEconomicsSkeleton />;
  if (!isAvailable(economics)) return <OpeningEconomicsEmpty economics={economics} title="Pokémon Opening Economics" subject="Opening Economics" />;
  const scope = economics.global;
  return <section data-opening-economics-overall>
    <Header scope={scope} marketDate={economics.marketDate} />
    <OpeningEconomicsDistribution scope={scope} targets={targets} />
    <details className={`${styles.surfaceQuiet} mt-3 rounded-xl px-4 py-3`} data-opening-economics-methodology>
      <summary className="cursor-pointer list-none text-xs font-medium text-[var(--text-primary)]">How this is calculated</summary>
      <ul className="mt-2.5 space-y-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">{METHODOLOGY.map((line) => <li key={line} className="flex gap-2"><span aria-hidden="true" className="mt-1.5 h-1 w-1 flex-none rounded-full bg-[rgb(var(--ex-teal))]" /><span>{line}</span></li>)}</ul>
    </details>
    <p className="mt-3 text-[0.68rem] leading-relaxed text-[var(--text-secondary)]">Card values reflect modeled gross market value. Selling fees, shipping, liquidity, grading costs, taxes, and other transaction costs are not deducted.</p>
  </section>;
}
