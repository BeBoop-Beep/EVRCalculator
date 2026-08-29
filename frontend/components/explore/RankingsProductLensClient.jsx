"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import DarkSelect from "@/components/ui/DarkSelect";
import SortMenuButton from "@/components/ui/SortMenuButton";
import TableSearchInput from "@/components/ui/TableSearchInput";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";
import {
  PremiumMetricLock,
  RankedProductIdentity,
} from "./RankedProductTablePrimitives.jsx";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { formatPublicRipScore } from "@/constants/exploreRankingConfig";
import styles from "./explore.module.css";

const FAMILY_ORDER = [
  "loose_booster_pack",
  "sleeved_booster_pack",
  "booster_bundle",
  "elite_trainer_box",
  "half_booster_box",
  "pokemon_center_elite_trainer_box",
  "booster_box",
  "enhanced_booster_box",
];
const SORTS = [
  { value: "overallRipLeaderScore", label: "Overall RIP" },
  { value: "financialRipLeaderScore", label: "Financial RIP" },
  { value: "collectorAppealScore", label: "Collector Appeal" },
  { value: "marketPrice", label: "Market Price" },
  { value: "expectedValue", label: "Expected Value" },
  { value: "chanceToRecoverCost", label: "Chance to Recover Cost" },
  { value: "alphabetical", label: "Alphabetical A–Z" },
];
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

function numeric(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function familyLabel(value) {
  const singular = String(value || "Product");
  if (singular === "Elite Trainer Box") return "Elite Trainer Boxes";
  if (singular === "Pokémon Center Elite Trainer Box") return "Pokémon Center Elite Trainer Boxes";
  if (singular === "Booster Box") return "Booster Boxes";
  if (singular === "Enhanced Booster Box") return "Enhanced Booster Boxes";
  return `${singular}s`;
}

function sortRows(rows, query, sortKey, direction) {
  const needle = String(query || "").trim().toLowerCase();
  const factor = direction === "asc" ? 1 : -1;
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => {
      if (!needle) return true;
      return [row?.productName, row?.setName]
        .some((value) => String(value || "").toLowerCase().includes(needle));
    })
    .slice()
    .sort((left, right) => {
      if (sortKey === "alphabetical") {
        return factor * (
          String(left?.productName || "").localeCompare(String(right?.productName || ""), "en", { sensitivity: "base" }) ||
          String(left?.setName || "").localeCompare(String(right?.setName || ""), "en", { sensitivity: "base" })
        );
      }
      const a = numeric(left?.[sortKey]);
      const b = numeric(right?.[sortKey]);
      if (a === null) return b === null ? 0 : 1;
      if (b === null) return -1;
      return factor * (a - b);
    });
}

function recovery(value) {
  const n = numeric(value);
  if (n === null) return "Unavailable";
  const probability = n > 1 ? n / 100 : n;
  return `${(probability * 100).toFixed(1)}%`;
}

function ProductRows({ rows, overall, entitled }) {
  if (!rows.length) {
    return <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">No products match the current filters.</p>;
  }
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className={styles.table}>
          <thead className={styles.head}>
            <tr>
              <th>Rank</th><th>Product / Set</th><th>Overall RIP</th><th>Tier</th>
              <th>Financial RIP</th><th>Collector Appeal</th><th>{overall ? "Unit Price" : "Market Price"}</th>
              <th>Expected Value</th><th>Chance to Recover Cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const rank = overall ? row?.budgetRank : row?.familyRank;
              const price = overall ? row?.unitPrice : row?.marketPrice;
              return (
                <tr key={row?.sealedProductId} className={styles.row}>
                  <td className={styles.numeric}>{entitled ? `#${rank ?? "—"}` : <PremiumMetricLock />}</td>
                  <td>
                    <Link href={buildSealedProductHref(row)} className={styles.rowLink}>
                      <RankedProductIdentity product={row} secondary={`${row?.setName || "Unknown set"} · ${row?.productFamilyLabel || "Product"}`} />
                    </Link>
                  </td>
                  <td className={styles.numeric}>{entitled ? <RipScoreBadge score={row?.overallRipLeaderScore} tier={row?.publicTier} /> : <PremiumMetricLock />}</td>
                  <td className="text-center">{entitled ? <RipTierMark tier={row?.publicTier} /> : <PremiumMetricLock />}</td>
                  <td className={styles.numeric}>{entitled && numeric(row?.financialRipLeaderScore) !== null ? `${formatPublicRipScore(row.financialRipLeaderScore)} / 10` : entitled ? "Unavailable" : <PremiumMetricLock />}</td>
                  <td className={styles.numeric}>{entitled && numeric(row?.collectorAppealScore) !== null ? `${formatPublicRipScore(row.collectorAppealScore)} / 10` : entitled ? "Unavailable" : <PremiumMetricLock />}</td>
                  <td className={styles.numeric}>{numeric(price) === null ? "Unavailable" : money.format(price)}</td>
                  <td className={styles.numeric}>{entitled ? (numeric(row?.expectedValue) === null ? "Unavailable" : money.format(row.expectedValue)) : <PremiumMetricLock />}</td>
                  <td className={styles.numeric}>{entitled ? recovery(row?.chanceToRecoverCost) : <PremiumMetricLock />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="space-y-2 p-3 md:hidden">
        {rows.map((row) => {
          const rank = overall ? row?.budgetRank : row?.familyRank;
          const price = overall ? row?.unitPrice : row?.marketPrice;
          return (
            <Link key={row?.sealedProductId} href={buildSealedProductHref(row)} className={`${styles.mobileRow} grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-2.5`}>
              <b className="text-right text-xs">{entitled ? `#${rank ?? "—"}` : "🔒"}</b>
              <div className="min-w-0">
                <RankedProductIdentity product={row} secondary={`${row?.setName || "Unknown set"} · ${row?.productFamilyLabel || "Product"}`} />
                <span className="mt-1 block text-xs tabular-nums text-[var(--text-secondary)]">{numeric(price) === null ? "Unavailable" : money.format(price)}</span>
              </div>
              {entitled ? <RipScoreBadge score={row?.overallRipLeaderScore} tier={row?.publicTier} compact /> : <PremiumMetricLock />}
            </Link>
          );
        })}
      </div>
    </>
  );
}

function LoadingPanel() {
  return <section className={`${styles.surface} set-glass-surface`} aria-busy="true"><p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">Loading product rankings…</p></section>;
}

export default function RankingsProductLensClient() {
  const { canViewRankingsIntelligence } = useRankingsAccess();
  const entitled = canViewRankingsIntelligence;
  const [state, setState] = useState({ status: "loading", productFamilyRankings: null, overallProductRankings: null });
  const [view, setView] = useState("allProducts");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState(entitled ? "overallRipLeaderScore" : "alphabetical");
  const [sortDirection, setSortDirection] = useState(entitled ? "desc" : "asc");
  const [budgetKey, setBudgetKey] = useState("full_market");
  const [overallResult, setOverallResult] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/explore/rankings/lens?lens=products", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok && response.status !== 503) throw new Error(payload?.message || "Unable to load product rankings");
        return payload;
      })
      .then((payload) => {
        setState({
          status: payload?.status === "available" ? "ready" : "unavailable",
          productFamilyRankings: payload?.productFamilyRankings || null,
          overallProductRankings: payload?.overallProductRankings || null,
        });
        setOverallResult(payload?.overallProductRankings || null);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setState({ status: "error", error: error.message, productFamilyRankings: null, overallProductRankings: null });
      });
    return () => controller.abort();
  }, []);

  const families = state.productFamilyRankings?.families || {};
  const familyEntries = useMemo(() => {
    const entries = Object.entries(families).filter(([, block]) => Number(block?.count) > 0);
    return entries.sort(([a], [b]) => {
      const ai = FAMILY_ORDER.indexOf(a), bi = FAMILY_ORDER.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [families]);

  const selectView = (next) => {
    setView(next);
    setQuery("");
    setSortKey(entitled ? "overallRipLeaderScore" : "alphabetical");
    setSortDirection(entitled ? "desc" : "asc");
  };

  const selectBudget = (next) => {
    setBudgetKey(next);
    setOverallResult((current) => ({ ...(current || {}), status: "loading" }));
    fetch(`/api/explore/product-rankings/overall?budget=${encodeURIComponent(next)}`, { cache: "no-store" })
      .then((response) => response.json())
      .then(setOverallResult)
      .catch(() => setOverallResult({ status: "unavailable", data: null }));
  };

  if (state.status === "loading") return <LoadingPanel />;
  if (state.status === "error" || state.status === "unavailable") {
    return <section className={`${styles.surface} set-glass-surface`}><p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">Product rankings are temporarily unavailable.</p></section>;
  }

  const selectedFamily = view === "allProducts" ? null : families[view];
  const sourceRows = view === "allProducts" ? (overallResult?.data?.rows || []) : (selectedFamily?.products || []);
  const rows = sortRows(sourceRows, query, sortKey, sortDirection);
  const budgetOptions = (overallResult?.data?.availableBudgets || []).map((entry) => ({
    value: entry?.type === "full_market" ? "full_market" : String(entry?.value),
    label: entry?.label,
  }));

  return (
    <>
      <nav aria-label="Product family" className="mb-3 flex gap-2 overflow-x-auto pb-1">
        <button type="button" onClick={() => selectView("allProducts")} aria-pressed={view === "allProducts"} className={`${styles.productFamilyTab} ${styles.productFamilyTabOverall} ${view === "allProducts" ? `${styles.productFamilyTabActive} ${styles.productFamilyTabOverallActive}` : ""}`}>◇ All Products</button>
        {familyEntries.map(([id, block]) => (
          <button key={id} type="button" onClick={() => selectView(id)} aria-pressed={view === id} className={`${styles.productFamilyTab} ${view === id ? styles.productFamilyTabActive : ""}`}>{familyLabel(block?.label)}</button>
        ))}
      </nav>
      <section className={`${styles.surface} set-glass-surface`}>
        <div className={`${styles.divider} grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_16rem_minmax(18rem,1fr)] md:items-center`}>
          <div>
            <h2 className="font-semibold text-[var(--text-primary)]">{view === "allProducts" ? "Best Products to Rip" : familyLabel(selectedFamily?.label)}</h2>
            <p className="text-xs text-[var(--text-secondary)]">{view === "allProducts" ? `${overallResult?.data?.cohortSize || rows.length} products ranked` : `${selectedFamily?.count || rows.length} products in this format`}</p>
          </div>
          <TableSearchInput value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search products or sets..." ariaLabel="Search products or sets" containerClassName="md:justify-self-center" />
          <div className="flex min-w-0 flex-col items-center gap-2 sm:flex-row md:justify-self-end">
            {view === "allProducts" && budgetOptions.length ? <DarkSelect ariaLabel="Opening Budget" value={budgetKey} onChange={selectBudget} options={budgetOptions} className="w-full md:min-w-[15rem]" triggerVariant="budget" eyebrow="Opening Budget" /> : null}
            <SortMenuButton ariaLabel="Sort products" value={sortKey} onChange={(next) => {
              if (!entitled && next !== "alphabetical") return;
              if (next === sortKey) setSortDirection((current) => current === "desc" ? "asc" : "desc");
              else { setSortKey(next); setSortDirection(next === "alphabetical" ? "asc" : "desc"); }
            }} options={SORTS.map((option) => ({ ...option, disabled: !entitled && option.value !== "alphabetical" }))} />
          </div>
        </div>
        {overallResult?.status === "loading" && view === "allProducts" ? <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">Loading this budget…</p> : <ProductRows rows={rows} overall={view === "allProducts"} entitled={entitled} />}
      </section>
    </>
  );
}
