"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ExploreTableClient from "./ExploreTableClient";
import SegmentedControl from "@/components/ui/SegmentedControl";
import OpeningEconomicsOverall from "./OpeningEconomicsOverall";
import OpeningEconomicsEras from "./OpeningEconomicsEras";
import EraRankings from "./EraRankings";
import SetPackMetrics from "./SetPackMetrics";
import CardChaseEfficiencyRankings from "./CardChaseEfficiencyRankings";
import DarkSelect from "@/components/ui/DarkSelect";
import SortMenuButton from "@/components/ui/SortMenuButton";
import TableSearchInput from "@/components/ui/TableSearchInput";
import InfoPopover, { PublicRipTierInfo } from "@/components/ui/InfoPopover";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";
import { PremiumMetricLock, RankedProductHeader, RankedProductIdentity } from "./RankedProductTablePrimitives.jsx";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import { getTierTone } from "@/lib/explore/interpretationTone";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import styles from "./explore.module.css";

const FAMILY_SORT_OPTIONS = [
  { value: "alphabetical", label: "Alphabetical A–Z" },
  { value: "overallRipLeaderScore", label: "Overall RIP" },
  { value: "financialRipLeaderScore", label: "Financial RIP" },
  { value: "collectorAppealScore", label: "Collector Appeal" },
  { value: "marketPrice", label: "Market Price" },
  { value: "expectedValue", label: "Expected Value" },
  { value: "chanceToRecoverCost", label: "Chance to Recover Cost" },
];
const OVERALL_SORT_OPTIONS = [
  { value: "alphabetical", label: "Alphabetical A–Z" },
  { value: "overallRipLeaderScore", label: "Overall RIP" },
  { value: "financialRipLeaderScore", label: "Financial RIP" },
  { value: "collectorAppealScore", label: "Collector Appeal" },
  { value: "unitPrice", label: "Unit Price" },
  { value: "expectedValue", label: "Expected Value" },
  { value: "chanceToRecoverCost", label: "Chance to Recover Cost" },
];
export const PRODUCT_FAMILY_NAV_ORDER = [
  "loose_booster_pack",
  "sleeved_booster_pack",
  "booster_bundle",
  "elite_trainer_box",
  "half_booster_box",
  "pokemon_center_elite_trainer_box",
  "booster_box",
  "enhanced_booster_box",
];
export function orderProductFamilyEntries(families) {
  const populated = Object.entries(families || {}).filter(
      ([, block]) => Number(block?.count) > 0,
    ),
    byId = new Map(populated),
    known = PRODUCT_FAMILY_NAV_ORDER.flatMap((id) =>
      byId.has(id) ? [[id, byId.get(id)]] : [],
    ),
    unknown = populated.filter(
      ([id]) => !PRODUCT_FAMILY_NAV_ORDER.includes(id),
    );
  if (unknown.length && typeof console !== "undefined")
    console.warn(
      "[product-rankings] unplaced product families",
      unknown.map(([id]) => id),
    );
  return [...known, ...unknown];
}
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const wholeMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const HELP = {
  overall:
    "Overall RIP follows a leader-anchored curve: the cohort leader is 10.0 and every other product shows its absolute score as a share of that leader.",
  financial:
    "Financial RIP uses its own leader-anchored curve: the financial leader is 10.0 and every other product is measured against it.",
  collector:
    "Collector Appeal is the set's canonical collector-facing appeal score. Unlike Overall RIP and Financial RIP here, it is not standardized against the selected product cohort.",
  market:
    "The current tracked market price used for this product's RIP calculations.",
  ev: "Average modeled value across simulated openings.",
  recovery:
    "The modeled probability that an opening returns at least the product's current market price.",
  format:
    "How this product ranks against other products in the same sealed-product format.",
};
const BUDGET_HELP =
  "Ranks whole-product opening strategies that fit within the selected spending limit. inDex compares the maximum number of whole units of each eligible product that can be opened within that budget. Unused money is not included in the RIP score. Full Market uses the current dynamic budget required to include every eligible modeled product.";

const number = (v) =>
  Number.isFinite(Number(v)) && v !== null && v !== "" ? Number(v) : null;
const pluralFamilyLabel = (label) =>
  ({
    "Elite Trainer Box": "Elite Trainer Boxes",
    "Pokémon Center Elite Trainer Box": "Pokémon Center Elite Trainer Boxes",
    "Booster Box": "Booster Boxes",
    "Enhanced Booster Box": "Enhanced Booster Boxes",
  })[label] || `${label}s`;

export function filterAndSortProducts(products, query, sortKey, sortDirection = "desc") {
  const needle = String(query || "")
      .trim()
      .toLocaleLowerCase(),
    key =
      sortKey === "overallRipScore"
        ? "overallRipLeaderScore"
        : sortKey === "financialRipScore"
          ? "financialRipLeaderScore"
          : sortKey;
  return (Array.isArray(products) ? products : [])
    .filter(
      (p) =>
        !needle ||
        [p?.productName, p?.setName].some((v) =>
          String(v || "")
            .toLocaleLowerCase()
            .includes(needle),
        ),
    )
    .slice()
    .sort((a, b) => {
      if (key === "alphabetical") {
        const direction = sortDirection === "desc" ? -1 : 1;
        return direction * (
          String(a?.productName || "").localeCompare(String(b?.productName || ""), "en", { sensitivity: "base" }) ||
          String(a?.setName || "").localeCompare(String(b?.setName || ""), "en", { sensitivity: "base" }) ||
          String(a?.sealedProductId || "").localeCompare(String(b?.sealedProductId || ""))
        );
      }
      const av = number(a?.[key]),
        bv = number(b?.[key]);
      if (av === null)
        return bv === null
          ? Number(a.budgetRank || a.familyRank) -
              Number(b.budgetRank || b.familyRank)
          : 1;
      if (bv === null) return -1;
      return (
        (sortDirection === "asc" ? av - bv : bv - av) ||
        Number(a.budgetRank || a.familyRank) -
          Number(b.budgetRank || b.familyRank)
      );
    });
}
const score = (v) =>
  number(v) === null ? "Unavailable" : `${formatPublicRipScore(v)} / 10`;
const recovery = (v) => {
  const n = number(v);
  return n === null
    ? "Unavailable"
    : `${(100 * (n > 1 ? n / 100 : n)).toFixed(1)}%`;
};
function productHref(p) {
  return buildSealedProductHref(p);
}
export function productFormatStrength(p) {
  const rank = number(p?.familyRank),
    size = number(p?.familySize),
    tier = String(p?.publicTier || "").toUpperCase();
  const heading =
    rank === 1
      ? "Format leader"
      : tier === "S"
        ? "Elite in format"
        : tier === "A"
          ? "Strong in format"
          : tier === "B"
            ? "Competitive in format"
            : "Ranks within format";
  return {
    heading,
    detail:
      rank && size
        ? `#${rank} of ${size} ${pluralFamilyLabel(p?.productFamilyLabel || "product")}`
        : "Format rank unavailable",
  };
}
function FormatStrength({ product: p }) {
  const text = productFormatStrength(p),
    tone = p?.publicTier ? getTierTone(p.publicTier) : null;
  return (
    <div
      data-product-format-strength
      className="flex min-w-[10rem] items-start gap-2.5"
    >
      <span
        aria-hidden="true"
        className="mt-1 h-2.5 w-2.5 flex-none rotate-45 border"
        style={{ borderColor: tone?.accentColor || "var(--accent)" }}
      />
      <span>
        <strong className="block text-xs text-[var(--text-primary)]">
          {text.heading}
        </strong>
        <span className="mt-1 block text-[10.5px] text-[var(--text-secondary)]">
          {text.detail}
        </span>
      </span>
    </div>
  );
}
function Strategy({ p }) {
  return (
    <span className="mt-1 block text-[10.5px] text-[var(--text-secondary)]">
      {p.quantity} {Number(p.quantity) === 1 ? "unit" : "units"} ·{" "}
      {money.format(p.actualCommittedCapital)} committed
    </span>
  );
}

function ProductIdentity({ product: p, overall, canViewProductRipIntelligence }) {
  return (
    <RankedProductIdentity product={p} secondary={`${p.setName} · ${p.productFamilyLabel}`}>
      {overall && canViewProductRipIntelligence ? <Strategy p={p} /> : null}
    </RankedProductIdentity>
  );
}

function ProductRankingsTable({
  products: sourceProducts,
  query,
  setQuery,
  sortKey,
  setSortKey,
  sortDirection,
  setSortDirection,
  title,
  subtitle,
  overall = false,
  budgetOptions = [],
  selectedBudgetKey = "",
  setSelectedBudgetKey,
  canViewProductRipIntelligence = false,
  onUnlockProductRip = null,
}) {
  const products = (sourceProducts || []).map((p) => ({
    ...p,
    overallRipScore: p.overallRipLeaderScore,
    financialRipScore: p.financialRipLeaderScore,
  }));
  const rank = (p) => (overall ? p.budgetRank : p.familyRank),
    tier = (p) => p.publicTier,
    price = overall ? "unitPrice" : "marketPrice",
    recover = "chanceToRecoverCost";
  return (
    <section
      className={`${styles.surface} set-glass-surface`}
      aria-label={`${title} rankings`}
    >
      <div
        className={`${styles.divider} grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_16rem_minmax(18rem,1fr)] md:items-center`}
      >
        <div>
          <div className="flex items-center gap-1.5">
            <h2 className="font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            {overall ? <InfoPopover text={BUDGET_HELP} /> : null}
          </div>
          <p className="text-xs text-[var(--text-secondary)]">{subtitle}</p>
        </div>
        <TableSearchInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search products or sets..."
          ariaLabel="Search products or sets"
          containerClassName="md:justify-self-center"
        />
        <div className="flex min-w-0 flex-col items-center gap-2 sm:flex-row md:justify-self-end">
          {overall ? (
            <DarkSelect
              ariaLabel="Opening Budget"
              value={selectedBudgetKey}
              onChange={setSelectedBudgetKey}
              options={budgetOptions}
              className="w-full md:min-w-[15rem]"
              triggerVariant="budget"
              eyebrow="Opening Budget"
            />
          ) : null}
          <SortMenuButton
            ariaLabel={canViewProductRipIntelligence
              ? `Sort products. Current sort: ${(overall ? OVERALL_SORT_OPTIONS : FAMILY_SORT_OPTIONS).find((option) => option.value === sortKey)?.label || "Overall RIP"}, ${sortDirection === "asc" ? "ascending" : "descending"}.`
              : "Sort products. Alphabetical sorting available; additional sorts require Index Plus."}
            value={sortKey}
            onChange={(next) => {
              if (!canViewProductRipIntelligence) return;
              if (next === sortKey) setSortDirection(sortDirection === "desc" ? "asc" : "desc");
              else { setSortKey(next); setSortDirection("desc"); }
            }}
            options={(overall ? OVERALL_SORT_OPTIONS : FAMILY_SORT_OPTIONS).map((option) => ({ ...option, disabled: !canViewProductRipIntelligence && option.value !== "alphabetical" }))}
            onLockedOption={onUnlockProductRip}
          />
        </div>
      </div>
      {products.length ? (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className={styles.table}>
              <colgroup><col className={styles.productRankColumn} /><col className={styles.productIdentityColumn} /><col span="8" /></colgroup>
              <caption className="sr-only">
                {title}. Sorting preserves official{" "}
                {overall ? "budget" : "family"} rank.
              </caption>
              <thead className={styles.head}>
                <tr>
                  <th>Rank</th>
                  <th>Product / Set</th>
                  <th>
                    <RankedProductHeader text={HELP.overall}>
                      Overall RIP
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader info={<PublicRipTierInfo />}>Tier</RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader text={HELP.financial}>
                      Financial RIP
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader text={HELP.collector}>
                      Collector Appeal
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader
                      text={
                        overall
                          ? "The current price of one natural product unit."
                          : HELP.market
                      }
                    >
                      {overall ? "Unit Price" : "Market Price"}
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader
                      text={
                        overall
                          ? "Expected value of the complete persisted multi-unit opening strategy."
                          : HELP.ev
                      }
                    >
                      Expected Value
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader
                      text={
                        overall
                          ? "Probability that the strategy recovers its actual committed capital, not the unused budget ceiling."
                          : HELP.recovery
                      }
                    >
                      Chance to Recover Cost
                    </RankedProductHeader>
                  </th>
                  <th>
                    <RankedProductHeader text={HELP.format}>
                      Format Strength
                    </RankedProductHeader>
                  </th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.sealedProductId} className={styles.row}>
                    <td className={styles.numeric}>{canViewProductRipIntelligence ? `#${rank(p)}` : <PremiumMetricLock />}</td>
                    <td className={styles.productIdentityCell}>
                      <Link href={productHref(p)} className={styles.rowLink}>
                        <ProductIdentity product={p} overall={overall} canViewProductRipIntelligence={canViewProductRipIntelligence} />
                      </Link>
                    </td>
                    <td className={styles.numeric}>
                      {canViewProductRipIntelligence ? <RipScoreBadge score={p.overallRipScore} tier={tier(p)} /> : <PremiumMetricLock />}
                    </td>
                    <td className="text-center">
                      {canViewProductRipIntelligence ? <RipTierMark tier={tier(p)} /> : <PremiumMetricLock />}
                    </td>
                    <td className={styles.numeric}>
                      {canViewProductRipIntelligence ? score(p.financialRipScore) : <PremiumMetricLock />}
                    </td>
                    <td className={styles.numeric}>
                      {canViewProductRipIntelligence ? score(p.collectorAppealScore) : <PremiumMetricLock />}
                    </td>
                    <td className={styles.numeric}>
                      {number(p[price]) === null
                        ? "Unavailable"
                        : money.format(p[price])}
                    </td>
                    <td className={styles.numeric}>
                      {canViewProductRipIntelligence ? (number(p.expectedValue) === null
                        ? "Unavailable"
                        : money.format(p.expectedValue)) : <PremiumMetricLock />}
                    </td>
                    <td className={styles.numeric}>{canViewProductRipIntelligence ? recovery(p[recover]) : <PremiumMetricLock />}</td>
                    <td>
                      {canViewProductRipIntelligence ? <FormatStrength product={p} /> : <PremiumMetricLock />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="space-y-2 p-3 md:hidden">
            {products.map((p) => (
              <Link
                key={p.sealedProductId}
                href={productHref(p)}
                className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto_auto] items-center gap-2.5`}
              >
                <b className="text-right">{canViewProductRipIntelligence ? `#${rank(p)}` : <PremiumMetricLock />}</b>
                <div className="min-w-0">
                  <ProductIdentity product={p} overall={overall} canViewProductRipIntelligence={canViewProductRipIntelligence} />
                  <span className="mt-1 block text-xs tabular-nums text-[var(--text-secondary)]">{number(p[price]) === null ? "Unavailable" : money.format(p[price])}</span>
                </div>
                {canViewProductRipIntelligence ? <RipScoreBadge
                  score={p.overallRipScore}
                  tier={tier(p)}
                  compact
                /> : <PremiumMetricLock />}
                {canViewProductRipIntelligence ? <RipTierMark tier={tier(p)} /> : <PremiumMetricLock />}
              </Link>
            ))}
          </div>
        </>
      ) : (
        <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">
          {overall
            ? "No eligible products match your search at this budget."
            : "No products match your search."}
        </p>
      )}
    </section>
  );
}
function OverallProductRankings({
  result,
  query,
  setQuery,
  sortKey,
  setSortKey,
  sortDirection,
  setSortDirection,
  selectedBudgetKey,
  setSelectedBudgetKey,
  canViewProductRipIntelligence,
  onUnlockProductRip,
}) {
  const overall = result?.data;
  const options = (overall?.availableBudgets || []).map((e) => ({
    value: e.type === "full_market" ? "full_market" : String(e.value),
    label: e.label,
  }));
  const products = useMemo(
    () => filterAndSortProducts(overall?.rows || [], query, sortKey, sortDirection),
    [overall?.rows, query, sortKey, sortDirection],
  );
  if (result?.status === "loading")
    return (
      <section className={`${styles.surface} set-glass-surface`}>
        <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">
          Loading Overall product rankings…
        </p>
      </section>
    );
  if (result?.status !== "available")
    return (
      <section className={`${styles.surface} set-glass-surface`}>
        <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">
          Overall product rankings are temporarily unavailable.
        </p>
      </section>
    );
  const selected = overall.selectedBudget;
  const context =
    selected?.type === "full_market"
      ? `Full Market · ${selected.label}`
      : `${wholeMoney.format(selected?.value)} Opening Budget`;
  return (
    <ProductRankingsTable
      products={products}
      query={query}
      setQuery={setQuery}
      sortKey={sortKey}
      setSortKey={setSortKey}
      sortDirection={sortDirection}
      setSortDirection={setSortDirection}
      title="Best Products to Rip"
      subtitle={`${context} · ${overall.cohortSize} products ranked`}
      overall
      budgetOptions={options}
      selectedBudgetKey={selectedBudgetKey}
      setSelectedBudgetKey={setSelectedBudgetKey}
      canViewProductRipIntelligence={canViewProductRipIntelligence}
      onUnlockProductRip={onUnlockProductRip}
    />
  );
}

export default function ProductFamilyRankingsClient({
  targets,
  productFamilyRankings,
  initialOverallProductRankings,
  loadError,
  openingEconomics = null,
  eraSetStrength = null,
  rankingsMarketDate = null,
  onUnlockProductRip = null,
}) {
  const { canViewRankingsIntelligence, canViewCardChaseEfficiency } = useRankingsAccess();
  const canViewProductRipIntelligence = canViewRankingsIntelligence;
  const families = productFamilyRankings?.families || {},
    entries = orderProductFamilyEntries(families);
  // The era a drilldown scoped the Sets lens to. Held here rather than inside
  // ExploreTableClient so the Eras lens can set it while navigating, and so
  // leaving the Sets lens does not silently strand an invisible filter.
  const [selectedEra, setSelectedEra] = useState(null);
  const [eraLens, setEraLens] = useState("economics");
  const [setLens, setSetLens] = useState("rankings");
  const [view, setView] = useState("economics"),
    [sortKey, setSortKey] = useState(canViewProductRipIntelligence ? "overallRipLeaderScore" : "alphabetical"),
    [sortDirection, setSortDirection] = useState(canViewProductRipIntelligence ? "desc" : "asc"),
    [query, setQuery] = useState(""),
    [selectedBudgetKey, setSelectedBudgetKey] = useState("full_market"),
    [overallResult, setOverallResult] = useState(
      initialOverallProductRankings || { status: "loading", data: null },
    );
  useEffect(() => {
    if (initialOverallProductRankings) return;
    let active = true;
    fetch("/api/explore/product-rankings/overall?budget=full_market")
      .then((r) => r.json())
      .then((v) => {
        if (active) setOverallResult(v);
      })
      .catch(() => {
        if (active) setOverallResult({ status: "unavailable", data: null });
      });
    return () => {
      active = false;
    };
  }, [initialOverallProductRankings]);
  const selectBudget = (next) => {
    setSelectedBudgetKey(next);
    setOverallResult((current) => ({ ...current, status: "loading" }));
    fetch(
      `/api/explore/product-rankings/overall?budget=${encodeURIComponent(next)}`,
    )
      .then((r) => r.json())
      .then(setOverallResult)
      .catch(() => setOverallResult({ status: "unavailable", data: null }));
  };
  const selected = families[view],
    products = useMemo(
      () => filterAndSortProducts(selected?.products, query, sortKey, sortDirection),
      [selected, query, sortKey, sortDirection],
    ),
    // Four top-level lenses. `view` still carries the product family key when a
    // family is selected, so the lens is derived from it rather than tracked in
    // a second piece of state that could disagree with it.
    productsActive = view !== "sets" && view !== "economics" && view !== "eras" && view !== "cards";
  const lens = view === "economics" ? "economics" : view === "eras" ? "eras" : view === "sets" ? "sets" : view === "cards" ? "cards" : "products";
  const selectView = (next) => {
      setQuery("");
      setSelectedEra(null);
      setSortKey(canViewProductRipIntelligence ? "overallRipLeaderScore" : "alphabetical");
      setSortDirection(canViewProductRipIntelligence ? "desc" : "asc");
      setView(next);
    },
    changeView = (next) =>
      selectView(next === "products" ? "allProducts" : next);
  return (
    <>
      <SegmentedControl
        className="mb-3 inline-block"
        ariaLabel="Ranking view"
        variant="primary"
        value={lens}
        onChange={changeView}
        mobileScroll
        options={[
          { value: "economics", label: "Overall" },
          { value: "eras", label: "Eras" },
          { value: "sets", label: "Sets" },
          { value: "products", label: "Products" },
          { value: "cards", label: "Cards" },
        ]}
      />
      {productsActive ? (
        <nav
          aria-label="Product family"
          className="mb-3 flex gap-2 overflow-x-auto pb-1"
        >
          <button
            type="button"
            onClick={() => selectView("allProducts")}
            aria-pressed={view === "allProducts"}
            data-overall-product-tab
            className={`${styles.productFamilyTab} ${styles.productFamilyTabOverall} ${view === "allProducts" ? `${styles.productFamilyTabActive} ${styles.productFamilyTabOverallActive}` : ""}`}
          >
            <span
              aria-hidden="true"
              className={styles.productFamilyTabOverallIcon}
            >
              ◇
            </span>
            All Products
          </button>
          {entries.map(([family, b]) => (
            <button
              key={family}
              type="button"
              onClick={() => selectView(family)}
              aria-pressed={view === family}
              className={`${styles.productFamilyTab} ${view === family ? styles.productFamilyTabActive : ""}`}
            >
              {pluralFamilyLabel(b.label)}
            </button>
          ))}
        </nav>
      ) : null}
      {(view === "eras" || view === "sets") ? (
        <nav aria-label={`${view === "eras" ? "Era" : "Set"} analysis`} className="mb-3 flex gap-2 overflow-x-auto pb-1" data-analysis-lens-tabs>
          {[{ value: "rankings", label: "Rankings" }, { value: "economics", label: "Pack Economics" }].map((option) => { const value = view === "eras" ? eraLens : setLens; const setValue = view === "eras" ? setEraLens : setSetLens; return <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => setValue(option.value)} className={`${styles.productFamilyTab} ${value === option.value ? styles.productFamilyTabActive : ""}`}>{option.label}</button>; })}
        </nav>
      ) : null}
      {view === "economics" ? (
        <OpeningEconomicsOverall economics={openingEconomics} targets={targets} onSelectEras={() => selectView("eras")} />
      ) : view === "eras" ? (
        eraLens === "rankings" ? <EraRankings contract={eraSetStrength} marketDate={rankingsMarketDate} onSelectEra={(era) => { setSetLens("rankings"); selectView("sets"); setSelectedEra(era?.eraName || null); }} /> : <OpeningEconomicsEras
          economics={openingEconomics}
          onSelectEra={(era) => {
            setSetLens("economics");
            selectView("sets");
            setSelectedEra(era?.eraName || null);
          }}
        />
      ) : view === "sets" ? (
        <>
          {selectedEra ? (
            <div className="mb-3 flex flex-wrap items-center gap-2" data-era-filter-chip>
              <span className="text-xs text-[var(--text-secondary)]">Showing sets from</span>
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]">
                {selectedEra}
                <button
                  type="button"
                  onClick={() => setSelectedEra(null)}
                  aria-label={`Clear the ${selectedEra} filter and show all sets`}
                  className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  <span aria-hidden="true">×</span>
                </button>
              </span>
            </div>
          ) : null}
          {setLens === "economics" ? <SetPackMetrics sets={openingEconomics?.sets} targets={targets} eraFilter={selectedEra} marketDate={openingEconomics?.marketDate} canViewRankingsIntelligence={canViewRankingsIntelligence} onUnlockProductRip={onUnlockProductRip} /> : <ExploreTableClient targets={targets} loadError={loadError} canViewProductRipIntelligence={canViewProductRipIntelligence} onUnlockProductRip={onUnlockProductRip} eraFilter={selectedEra} marketDate={rankingsMarketDate} />}
        </>
      ) : view === "cards" ? (
        <CardChaseEfficiencyRankings entitled={canViewCardChaseEfficiency} targets={targets} />
      ) : view === "allProducts" ? (
        <OverallProductRankings
          result={overallResult}
          query={query}
          setQuery={setQuery}
          sortKey={sortKey}
          setSortKey={setSortKey}
          sortDirection={sortDirection}
          setSortDirection={setSortDirection}
          selectedBudgetKey={selectedBudgetKey}
          setSelectedBudgetKey={selectBudget}
          canViewProductRipIntelligence={canViewProductRipIntelligence}
          onUnlockProductRip={onUnlockProductRip}
        />
      ) : (
        <ProductRankingsTable
          products={products}
          query={query}
          setQuery={setQuery}
          sortKey={sortKey}
          setSortKey={setSortKey}
          sortDirection={sortDirection}
          setSortDirection={setSortDirection}
          title={`Best ${pluralFamilyLabel(selected?.label)} to Rip`}
          subtitle={`Compared only with ${pluralFamilyLabel(selected?.label)} · ${selected?.count} products ranked`}
          canViewProductRipIntelligence={canViewProductRipIntelligence}
          onUnlockProductRip={onUnlockProductRip}
        />
      )}
    </>
  );
}
