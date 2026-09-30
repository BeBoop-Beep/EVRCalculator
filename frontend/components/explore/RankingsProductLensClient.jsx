"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import InfoPopover from "@/components/ui/InfoPopover";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes.mjs";
import { readProductRankings } from "@/lib/rankings/productRankingsClient.mjs";
import { readPublicProductCatalogue } from "@/lib/rankings/rankingsPublicClient.mjs";
import { beginLastGoodRefresh, failLastGoodRefresh } from "@/lib/rankings/rankingsLastGoodState.mjs";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import AnalyticsTableShell from "./AnalyticsTableShell";
import { RankedProductIdentity } from "./RankedProductTablePrimitives.jsx";
import { RankingsRipScoreBadge } from "./RankingsScorePrimitives";
import { bestOpenGap, filterProductRows, productFamilyOptions, sortProductRows } from "./productRankingsPresentation.mjs";
import styles from "./explore.module.css";

const VIEW_OPTIONS = [{ value: "scores", label: "Scores" }, { value: "economics", label: "Economics" }];
const SCORE_SORTS = { rank: "Rank", productName: "Product", ripScore: "RIP Score", financialRip: "Financial", setChaseAccessibility: "Set Chase", parentSetCollector: "Set Collector" };
const ECONOMICS_SORTS = { productName: "Product", unitPrice: "Unit Price", bestOpenPrice: "Best-Open Price", expectedValuePerPack: "EV / Pack", modeledReturnOnSpend: "Modeled Return", chanceToRecoverCost: "Recover Cost" };
const DEFINITIONS = {
  financialRip: "Absolute Product Financial RIP authority. This is not a Benchmark /10 score.",
  setChaseAccessibility: "Chase Accessibility inherited from this Product's parent Set.",
  parentSetCollector: "Collector Appeal inherited from this Product's parent Set.",
  unitPrice: "Current unit price used by the prepared Product economics contract.",
  bestOpenPrice: "The highest modeled purchase price where opening this exact Product still meets its Best-Open comparison threshold.",
  expectedValuePerPack: "Average modeled card value per pack.",
  modeledReturnOnSpend: "Modeled card value divided by purchase cost.",
  chanceToRecoverCost: "Modeled chance that an opening recovers its purchase cost.",
};
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const number = (value) => value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const currency = (value) => number(value) === null ? "—" : money.format(Number(value));
const percent = (value) => number(value) === null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
const metric = (value) => number(value) === null ? "—" : Number(value).toFixed(1);
const renderable = (state) => state?.status === "ready" && state?.contract?.status === "available" && Array.isArray(state.contract.rows);
const productForIdentity = (row) => ({ ...row, productFamily: row.familyKey, productFamilyLabel: row.familyName });
const productSecondary = (row) => `${row.setName || "Unknown set"} · ${row.familyName || "Product"}`;

function ProductLink({ row }) { return <Link href={buildSealedProductHref(row) || "#"} className={styles.rowLink}><RankedProductIdentity product={productForIdentity(row)} secondary={productSecondary(row)} /></Link>; }
function Metric({ label, value }) { return <div><dt className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">{label}</dt><dd className="mt-0.5 font-semibold tabular-nums text-[var(--text-primary)]">{value}</dd></div>; }
function Empty() { return <p className="px-4 py-12 text-center text-sm text-[var(--text-secondary)]">No Products match the current filters.</p>; }
function LoadingPanel({ view }) { return <section className={`${styles.surface} min-h-64 p-5`} aria-busy="true"><div className="h-5 w-52 animate-pulse rounded bg-white/10" /><p className="sr-only">Loading Product {view}</p><div className="mt-5 h-40 animate-pulse rounded-xl bg-white/[.045]" /></section>; }

function SortHeader({ columnKey, label, sort, onSort, info }) {
  return <th className={columnKey === "productName" ? "" : styles.numeric} aria-sort={sort.key === columnKey ? sort.direction === "asc" ? "ascending" : "descending" : undefined}><span className={`inline-flex items-center gap-1 ${columnKey === "productName" ? "" : "justify-end"}`}><button type="button" className={styles.sortButton} onClick={() => onSort(columnKey)}>{label}</button>{info ? <InfoPopover text={info} /> : null}</span></th>;
}

function ScoresTable({ rows, sort, onSort }) {
  if (!rows.length) return <Empty />;
  return <><div className="hidden overflow-x-auto desk:block"><table className={`${styles.table} ${styles.productScoresTable}`} data-product-scores-table><caption className="sr-only">Product Scores ranked across the current Full Market cohort.</caption><colgroup><col className={styles.productRankColumn} /><col className={styles.productIdentityColumn} /><col className={styles.productRipColumn} /><col span="3" className={styles.productMetricColumn} /></colgroup><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr>{Object.entries(SCORE_SORTS).map(([key, label]) => <SortHeader key={key} columnKey={key} label={label} sort={sort} onSort={onSort} info={DEFINITIONS[key]} />)}</tr></thead><tbody>{rows.map((row) => <tr key={row.sealedProductId} className={styles.row}><td className={styles.numeric}><span aria-label={`Rank ${row.rank} of ${row.cohortSize} in the Full Market cohort`}>#{row.rank ?? "—"}</span></td><td><ProductLink row={row} /></td><td className={styles.numeric}><RankingsRipScoreBadge metric={row.ripScore} benchmarkLabel="Full Market 5.0 reference" /></td><td className={styles.numeric}>{metric(row.financialRip)}</td><td className={styles.numeric}>{metric(row.setChaseAccessibility)}</td><td className={styles.numeric}>{metric(row.parentSetCollector)}</td></tr>)}</tbody></table></div><div className="space-y-2 p-3 desk:hidden">{rows.map((row) => <article key={row.sealedProductId} className={styles.mobileRow} data-product-score-card><div className="flex items-start justify-between gap-3"><div className="min-w-0"><span className="text-xs font-semibold tabular-nums text-[var(--text-secondary)]" aria-label={`Rank ${row.rank} of ${row.cohortSize} in the Full Market cohort`}>#{row.rank ?? "—"}</span><ProductLink row={row} /></div><RankingsRipScoreBadge metric={row.ripScore} benchmarkLabel="Full Market 5.0 reference" compact /></div><dl className="mt-3 grid grid-cols-3 gap-2 border-t border-[var(--border-subtle)] pt-3 text-xs"><Metric label="Financial" value={metric(row.financialRip)} /><Metric label="Set Chase" value={metric(row.setChaseAccessibility)} /><Metric label="Set Collector" value={metric(row.parentSetCollector)} /></dl></article>)}</div></>;
}

function BestOpen({ row }) { const gap = bestOpenGap(row); return <><strong className="block text-[var(--text-primary)]">{currency(row.bestOpenPrice)}</strong>{gap ? <span className="mt-0.5 block text-[10px] font-normal text-[var(--text-secondary)]">{gap}</span> : null}</>; }

function EconomicsTable({ rows, sort, onSort }) {
  if (!rows.length) return <Empty />;
  return <><div className="hidden overflow-x-auto desk:block"><table className={`${styles.table} ${styles.productEconomicsTable}`} data-product-economics-table><caption className="sr-only">Product Economics with exact Product Best-Open thresholds.</caption><colgroup><col className={styles.productIdentityColumn} /><col span="5" className={styles.productEconomicsColumn} /></colgroup><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr>{Object.entries(ECONOMICS_SORTS).map(([key, label]) => <SortHeader key={key} columnKey={key} label={label} sort={sort} onSort={onSort} info={DEFINITIONS[key]} />)}</tr></thead><tbody>{rows.map((row) => <tr key={row.sealedProductId} className={styles.row}><td><ProductLink row={row} /></td><td className={styles.numeric}>{currency(row.unitPrice)}</td><td className={styles.numeric}><BestOpen row={row} /></td><td className={styles.numeric}>{currency(row.expectedValuePerPack)}</td><td className={styles.numeric}>{percent(row.modeledReturnOnSpend)}</td><td className={styles.numeric}>{percent(row.chanceToRecoverCost)}</td></tr>)}</tbody></table></div><div className="space-y-2 p-3 desk:hidden">{rows.map((row) => <article key={row.sealedProductId} className={styles.mobileRow} data-product-economics-card><ProductLink row={row} /><dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-[var(--border-subtle)] pt-3 text-sm"><Metric label="Unit Price" value={currency(row.unitPrice)} /><Metric label="Best-Open" value={<BestOpen row={row} />} /><Metric label="EV / Pack" value={currency(row.expectedValuePerPack)} /><Metric label="Modeled Return" value={percent(row.modeledReturnOnSpend)} /><Metric label="Recover Cost" value={percent(row.chanceToRecoverCost)} /></dl></article>)}</div></>;
}

const LockedCell = () => <span className="text-xs font-medium text-[var(--text-secondary)]" aria-label="Requires Index Plus">Locked</span>;
function PublicScoresTable({ rows }) {
  if (!rows.length) return <Empty />;
  return <><div className="hidden overflow-x-auto desk:block"><table className={`${styles.table} ${styles.productScoresTable}`} data-product-public-catalogue><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr><th>Product</th><th className={styles.numeric}>RIP Score</th><th className={styles.numeric}>Financial</th><th className={styles.numeric}>Set Chase</th><th className={styles.numeric}>Set Collector</th></tr></thead><tbody>{rows.map((row) => <tr key={row.sealedProductId} className={styles.row}><td><ProductLink row={row} /></td>{[0,1,2,3].map((key) => <td key={key} className={styles.numeric}><LockedCell /></td>)}</tr>)}</tbody></table></div><div className="space-y-2 p-3 desk:hidden">{rows.map((row) => <article key={row.sealedProductId} className={styles.mobileRow}><ProductLink row={row} /><p className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-xs text-[var(--text-secondary)]">Score analytics: <LockedCell /></p></article>)}</div></>;
}
function PublicEconomicsTable({ rows }) {
  if (!rows.length) return <Empty />;
  return <><div className="hidden overflow-x-auto desk:block"><table className={`${styles.table} ${styles.productEconomicsTable}`} data-product-public-catalogue><thead className={`${styles.head} ${styles.analyticsTableHead}`}><tr><th>Product</th>{["Unit Price", "Best-Open Price", "EV / Pack", "Modeled Return", "Recover Cost"].map((label) => <th key={label} className={styles.numeric}>{label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.sealedProductId} className={styles.row}><td><ProductLink row={row} /></td>{[0,1,2,3,4].map((key) => <td key={key} className={styles.numeric}><LockedCell /></td>)}</tr>)}</tbody></table></div><div className="space-y-2 p-3 desk:hidden">{rows.map((row) => <article key={row.sealedProductId} className={styles.mobileRow}><ProductLink row={row} /><p className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-xs text-[var(--text-secondary)]">Economics analytics: <LockedCell /></p></article>)}</div></>;
}

function freshnessContext(contract) {
  const dated = (contract?.rows || []).filter((row) => row.bestOpenSourceMarketDate);
  if (!dated.length) return "Full Market pricing";
  const newest = [...dated].sort((a, b) => String(b.bestOpenSourceMarketDate).localeCompare(String(a.bestOpenSourceMarketDate)))[0];
  const label = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${newest.bestOpenSourceMarketDate}T00:00:00Z`));
  return `Best-Open as of ${label}${dated.some((row) => row.bestOpenFreshnessStatus === "older") ? " · independently dated" : ""}`;
}

export default function RankingsProductLensClient({ sessionCache }) {
  const { canViewRankingsIntelligence, authStatus } = useRankingsAccess();
  const [view, setView] = useState("scores");
  const [states, setStates] = useState({ scores: { status: "idle", contract: null }, economics: { status: "idle", contract: null } });
  const [catalogue, setCatalogue] = useState({ status: "idle", contract: null });
  const [family, setFamily] = useState("all");
  const [query, setQuery] = useState("");
  const [sorts, setSorts] = useState({ scores: { key: "rank", direction: "asc" }, economics: { key: "unitPrice", direction: "desc" } });
  const load = useCallback(async (target, { force = false } = {}) => {
    if (!canViewRankingsIntelligence) return null;
    setStates((current) => ({ ...current, [target]: beginLastGoodRefresh(current[target], renderable) }));
    try {
      const contract = await readProductRankings(target, { sessionCache, force });
      setStates((current) => ({ ...current, [target]: { status: "ready", contract, refreshing: false, refreshError: null } }));
      return contract;
    } catch (error) {
      setStates((current) => ({ ...current, [target]: failLastGoodRefresh(current[target], error, renderable, { contract: null }) }));
      return null;
    }
  }, [canViewRankingsIntelligence, sessionCache]);
  const active = states[view];
  useEffect(() => {
    let live = true;
    setCatalogue((current) => current.status === "ready" ? current : { status: "loading", contract: null });
    readPublicProductCatalogue({ sessionCache }).then((contract) => {
      if (live) setCatalogue({ status: "ready", contract });
    }).catch((error) => { if (live) setCatalogue({ status: "error", contract: null, error: error.message }); });
    return () => { live = false; };
  }, [sessionCache]);
  useEffect(() => { if ((authStatus === "resolved" || authStatus === "degraded") && canViewRankingsIntelligence && active.status === "idle") load(view); }, [active.status, authStatus, canViewRankingsIntelligence, load, view]);
  useEffect(() => { if (!canViewRankingsIntelligence) setStates({ scores: { status: "idle", contract: null }, economics: { status: "idle", contract: null } }); }, [canViewRankingsIntelligence]);
  const publicMode = (authStatus === "resolved" || authStatus === "degraded") ? !canViewRankingsIntelligence : true;
  const rawRows = useMemo(() => publicMode ? catalogue.contract?.rows || [] : active.contract?.rows || [], [active.contract, catalogue.contract, publicMode]);
  const familyRows = useMemo(() => publicMode ? rawRows : rawRows.length ? rawRows : states.scores.contract?.rows || states.economics.contract?.rows || [], [publicMode, rawRows, states.economics.contract, states.scores.contract]);
  const familyOptions = useMemo(() => productFamilyOptions(familyRows), [familyRows]);
  useEffect(() => { if (family !== "all" && !familyOptions.some((option) => option.value === family)) setFamily("all"); }, [family, familyOptions]);
  const filtered = useMemo(() => filterProductRows(rawRows, { query, family }), [family, query, rawRows]);
  const sort = sorts[view];
  const rows = useMemo(() => publicMode ? [...filtered].sort((a, b) => String(a.productName || "").localeCompare(String(b.productName || "")) || String(a.sealedProductId).localeCompare(String(b.sealedProductId))) : sortProductRows(filtered, sort.key, sort.direction), [filtered, publicMode, sort]);
  const changeSort = (key) => setSorts((current) => ({ ...current, [view]: { key, direction: current[view].key === key && current[view].direction === "asc" ? "desc" : "asc" } }));
  const controls = <><SegmentedControl className="mb-3 w-full max-w-xs" ariaLabel="Product Rankings view" value={view} onChange={setView} options={VIEW_OPTIONS} equalWidth mobileFullWidth /><nav aria-label="Product family" className="mb-3 flex gap-2 overflow-x-auto pb-1"><button type="button" onClick={() => setFamily("all")} aria-pressed={family === "all"} className={`${styles.productFamilyTab} ${family === "all" ? styles.productFamilyTabActive : ""}`}>All Products</button>{familyOptions.map((option) => <button key={option.value} type="button" onClick={() => setFamily(option.value)} aria-pressed={family === option.value} className={`${styles.productFamilyTab} ${family === option.value ? styles.productFamilyTabActive : ""}`}>{option.label}</button>)}</nav></>;
  if (publicMode && catalogue.status !== "ready") return <>{controls}<LoadingPanel view={view} /></>;
  if (!publicMode && (active.status === "idle" || active.status === "loading")) return <>{controls}<LoadingPanel view={view} /></>;
  if (!publicMode && active.status === "error") return <>{controls}<section className={`${styles.surface} p-5 text-sm text-[var(--text-secondary)]`}>Product {view === "scores" ? "Scores" : "Economics"} are temporarily unavailable. <button type="button" className="ml-2 underline" onClick={() => load(view, { force: true })}>Retry</button></section></>;
  const title = view === "scores" ? "Product Scores" : "Product Economics";
  const context = publicMode ? "Alphabetical Product catalogue" : view === "scores" ? "Ranks use the current Full Market product cohort · Full Market pricing" : freshnessContext(active.contract);
  return <>{controls}<AnalyticsTableShell title={title} info={publicMode ? "Product identity and type are public. Ranking, score, and economics values require Index Plus." : view === "scores" ? "RIP Score uses the backend Benchmark presentation. Financial is an absolute metric; Set Chase and Set Collector are inherited from the parent Set." : "Exact Product economics from the dedicated prepared contract. Best-Open thresholds are not reconstructed in the browser."} query={query} onQueryChange={(event) => setQuery(event.target.value)} searchPlaceholder="Search Products…" searchLabel="Search Products" context={context} shown={rows.length} ranked={!publicMode && view === "scores" ? rawRows.length : null} marketDate={publicMode ? null : active.contract?.marketDate || null}>{publicMode ? view === "scores" ? <PublicScoresTable rows={rows} /> : <PublicEconomicsTable rows={rows} /> : view === "scores" ? <ScoresTable rows={rows} sort={sort} onSort={changeSort} /> : <EconomicsTable rows={rows} sort={sort} onSort={changeSort} />}{!publicMode && active.refreshError ? <p role="status" className="px-4 py-2 text-xs text-[var(--text-secondary)]">Refresh failed; showing the last available Product {view}.</p> : null}</AnalyticsTableShell></>;
}
