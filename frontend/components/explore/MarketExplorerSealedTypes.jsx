"use client";
import { useMemo, useState } from "react";
import { normalizeQuerySpec, QUERY_ASSET_SEALED } from "@/lib/explore/marketExplorerQuery.mjs";
import {
  ASSET_OPTION_ACTION,
  NO_APPROVED_SEALED_QUICK_COPY,
  approvedSealedQuickMarkets,
  normalizeSealedTypeOptions,
} from "@/lib/explore/marketExplorerAssetOptions.mjs";

const clean = (value) => String(value || "").trim().toLowerCase();

/**
 * Sealed Types: a semantically sealed component (not the rarity component
 * relabelled). Renders whatever the DB publishes -- the family list is never
 * hard-coded here -- and gives every option an explicit, truthful action.
 * Also renders the Sealed Quick Markets section: with zero APPROVED entries it
 * says so; proposed definitions are never selectable.
 */
export default function MarketExplorerSealedTypes({
  options = null,
  status = "ready",
  activeKeys = [],
  pendingKeys = [],
  activeSeries = [],
  canBuild = false,
  onUpgrade,
  onSelect,
  onAddQuery,
  onRemoveQuery,
  onRetry,
  // V1 mode: the published sealed-format rows (Booster Boxes, ETBs, Packs, ...) are shown
  // INSIDE this category; V2 types come from the asset-options registry.
  v2Mode = true,
  formatMarkets = [],
}) {
  const [search, setSearch] = useState("");
  const [pendingId, setPendingId] = useState(null);
  const [message, setMessage] = useState("");
  const types = useMemo(() => normalizeSealedTypeOptions(options), [options]);
  const filtered = useMemo(() => types.filter((t) => !search || clean(t.label).includes(clean(search))), [types, search]);
  const queryFor = (type) => activeSeries.find((s) => s?.spec?.asset === QUERY_ASSET_SEALED && s.spec.mode === "all"
    && (s.spec.segmentIds || []).length === 1 && s.spec.segmentIds[0] === type.id
    && !(s.spec.eraIds || []).length && !(s.spec.setIds || []).length) || null;

  const act = async (type) => {
    setMessage("");
    if (type.action === ASSET_OPTION_ACTION.prepared) { onSelect?.(type.marketKey); return; }
    if (type.action !== ASSET_OPTION_ACTION.build) return;
    const existing = queryFor(type);
    if (existing) { onRemoveQuery?.(existing.key); return; }
    if (!canBuild) { onUpgrade?.(); return; }
    setPendingId(type.id);
    try {
      const outcome = await onAddQuery?.(normalizeQuerySpec({ asset: QUERY_ASSET_SEALED, segmentIds: [type.id], mode: "all" }));
      if (outcome === "duplicate") setMessage("That sealed market is already active.");
    } catch (error) {
      setMessage(error?.message || "Unable to add this sealed market.");
    } finally { setPendingId(null); }
  };

  return <section data-market-explorer-sealed-types className="py-2" aria-labelledby="sealed-types-heading">
    <h3 id="sealed-types-heading" className="text-xs font-semibold text-[var(--text-primary)]">Sealed Types</h3>
    <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">Product-family markets. Bulk containers such as Cases and Displays are separate markets and are not part of Total Sealed.</p>
    {!v2Mode ? <>
      {formatMarkets.length ? <ul data-sealed-v1-formats className="mt-2 space-y-1" aria-label="Published sealed types">
        {formatMarkets.map((market) => {
          const active = activeKeys.includes(market.market_key);
          const pending = pendingKeys.includes(market.market_key);
          return <li key={market.market_key} data-sealed-type={market.market_key} data-sealed-type-action="prepared" className={`rounded-md border-l-2 ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)]" : "border-transparent"}`}>
            <button type="button" data-prepared-market={market.market_key} aria-pressed={active} disabled={pending} onClick={() => onSelect?.(market.market_key)} className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs text-[var(--text-primary)]"><span className="min-w-0 truncate">{market.label}{active ? <span aria-label="Active market"> ✓</span> : null}</span>{pending ? <span className="text-[10px] text-[var(--text-secondary)]">Adding…</span> : null}</button>
          </li>;
        })}
      </ul> : <p data-sealed-awaiting="types" className="mt-2 text-[11px] text-[var(--text-secondary)]">Sealed Type markets are awaiting the next prepared market generation.</p>}
      <p data-sealed-types-awaiting-more className="mt-2 text-[10px] text-[var(--text-secondary)]">Further Sealed Types (such as Cases, Displays and Elite Trainer Boxes) appear here as they are published in the next prepared market generation.</p>
    </> : null}
    {v2Mode && status === "unavailable" ? <div role="alert" data-sealed-types-state="unavailable" className="mt-2 flex items-center justify-between gap-2 text-[11px] text-[var(--text-secondary)]"><span>Sealed types are temporarily unavailable.</span>{onRetry ? <button type="button" onClick={onRetry} className="rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold">Retry</button> : null}</div> : null}
    {v2Mode && status === "loading" && !types.length ? <p role="status" className="mt-2 text-[11px] text-[var(--text-secondary)]">Loading sealed types…</p> : null}
    {v2Mode && types.length ? <>
      <input type="search" data-sealed-type-search value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search sealed types…" aria-label="Search sealed types" className="mt-2 min-h-9 w-full rounded-md border border-[var(--border-subtle)] bg-transparent px-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70" />
      <ul className="mt-1 max-h-72 space-y-1 overflow-y-auto pr-1" aria-label="Sealed types">
        {filtered.map((type) => {
          const executable = type.action !== ASSET_OPTION_ACTION.none;
          const query = queryFor(type);
          const active = (type.marketKey && activeKeys.includes(type.marketKey)) || Boolean(query);
          const pending = pendingId === type.id || Boolean(type.marketKey && pendingKeys.includes(type.marketKey));
          return <li key={type.id} data-sealed-type={type.id} data-sealed-type-state={type.state} data-sealed-type-action={type.action} className={`rounded-md border-l-2 px-2 py-1.5 ${active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)]" : "border-transparent"}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-xs text-[var(--text-primary)]">{type.label}</span>
              {executable
                ? <button type="button" data-sealed-type-action-button={type.id} disabled={pending} onClick={() => act(type)} className="flex-none rounded border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-primary)]">{pending ? "Adding…" : active ? "Remove" : type.action === ASSET_OPTION_ACTION.build && !canBuild ? "Build · Premium" : "+ Compare"}</button>
                : <span data-sealed-type-unavailable className="flex-none text-[10px] font-semibold text-[var(--text-secondary)]">Unavailable</span>}
            </div>
            {!executable && type.reason ? <p data-sealed-type-reason className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{type.reason}</p> : null}
            {type.note ? <p data-sealed-type-note className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{type.note}</p> : null}
          </li>;
        })}
        {!filtered.length ? <li className="px-2 py-2 text-xs text-[var(--text-secondary)]">No matching sealed type.</li> : null}
      </ul>
    </> : null}
    {message ? <p role="alert" className="mt-2 text-[10px] text-[var(--text-secondary)]">{message}</p> : null}
  </section>;
}

/** Sealed Quick Markets. Only APPROVED registry entries are ever selectable. */
export function MarketExplorerSealedQuickMarkets({ options = null, activeKeys = [], onSelect }) {
  const quick = approvedSealedQuickMarkets(options);
  return <section data-market-explorer-sealed-quick className="py-2" aria-labelledby="sealed-quick-heading">
    <h3 id="sealed-quick-heading" className="text-xs font-semibold text-[var(--text-primary)]">Quick Markets</h3>
    {quick.length
      ? <ul className="mt-1 space-y-1">{quick.map((q) => <li key={q.key}><button type="button" data-sealed-quick-market={q.key} aria-pressed={activeKeys.includes(q.key)} onClick={() => onSelect?.(q.key)} className="w-full rounded border border-[var(--border-subtle)] px-2 py-1.5 text-left text-xs text-[var(--text-primary)]">{q.label}</button></li>)}</ul>
      : <p data-sealed-quick-empty className="mt-1 text-[11px] text-[var(--text-secondary)]">{NO_APPROVED_SEALED_QUICK_COPY}</p>}
  </section>;
}
