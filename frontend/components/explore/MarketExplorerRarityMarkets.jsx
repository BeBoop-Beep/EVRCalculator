"use client";
import React, { useMemo, useState } from "react";
import { normalizeQuerySpec, QUERY_ASSET_CARDS } from "../../lib/explore/marketExplorerQuery.mjs";

const clean = (value) => String(value || "").trim().toLowerCase();
const isSingleRarityQuery = (series, segmentId) => {
  const spec = series?.spec;
  return spec?.asset === QUERY_ASSET_CARDS
    && spec?.mode === "all"
    && (spec?.segmentIds || []).length === 1
    && spec.segmentIds[0] === segmentId
    && !(spec?.eraIds || []).length
    && !(spec?.setIds || []).length
    && !(spec?.pokemonIds || []).length
    && !(spec?.priceSegmentIds || []).length
    && !(spec?.releaseAgeCohortIds || []).length;
};

export default function MarketExplorerRarityMarkets({
  directory = [],
  rarityOptions = [],
  activeKeys = [],
  activeSeries = [],
  canUse = false,
  onUpgrade,
  onSelect,
  onAddQuery,
  onRemoveQuery,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [pendingId, setPendingId] = useState(null);
  const [message, setMessage] = useState("");

  const preparedBySegment = useMemo(() => {
    const map = new Map();
    for (const market of directory) {
      if (market?.market_type !== "prepared_rarity") continue;
      const segmentId = market?.metadata?.segmentId;
      if (segmentId) map.set(String(segmentId), market);
    }
    return map;
  }, [directory]);

  // Some older prepared generations did not expose segmentId in metadata.
  // Label matching keeps those fast paths usable while the canonical options
  // remain the complete source of what rarities are selectable.
  const preparedByLabel = useMemo(() => new Map(
    directory
      .filter((market) => market?.market_type === "prepared_rarity")
      .map((market) => [clean(market.label), market]),
  ), [directory]);

  const options = useMemo(() => {
    const canonical = (Array.isArray(rarityOptions) ? rarityOptions : [])
      .map((entry) => ({
        id: String(entry.key || entry.id || ""),
        label: String(entry.label || entry.name || entry.key || entry.id || ""),
      }))
      .filter((entry) => entry.id && entry.label);
    if (canonical.length) return canonical;
    return directory
      .filter((market) => market?.market_type === "prepared_rarity")
      .map((market) => ({ id: String(market?.metadata?.segmentId || market.market_key), label: market.label }));
  }, [directory, rarityOptions]);

  const filtered = useMemo(() => {
    const needle = clean(search);
    return options.filter((entry) => !needle || clean(entry.label).includes(needle));
  }, [options, search]);

  const stateFor = (option) => {
    const prepared = preparedBySegment.get(option.id) || preparedByLabel.get(clean(option.label)) || null;
    const preparedActive = prepared ? activeKeys.includes(prepared.market_key) : false;
    const query = activeSeries.find((series) => isSingleRarityQuery(series, option.id)) || null;
    return { prepared, preparedActive, query, active: preparedActive || Boolean(query) };
  };

  const toggle = async (option) => {
    const state = stateFor(option);
    setMessage("");
    if (state.prepared) {
      onSelect?.(state.prepared.market_key);
      return;
    }
    if (state.query) {
      onRemoveQuery?.(state.query.key);
      return;
    }
    if (!canUse) {
      onUpgrade?.();
      return;
    }
    setPendingId(option.id);
    try {
      const outcome = await onAddQuery?.(normalizeQuerySpec({
        asset: QUERY_ASSET_CARDS,
        segmentIds: [option.id],
        mode: "all",
      }));
      if (outcome === "duplicate") setMessage("That rarity market is already active.");
    } catch (error) {
      setMessage(error?.message || "Unable to add this rarity market.");
    } finally {
      setPendingId(null);
    }
  };

  const activeCount = options.filter((option) => stateFor(option).active).length;
  const openDirectory = (category) => {
    const button = document.querySelector(`[data-market-directory-category="${category}"]`);
    button?.click();
    button?.focus();
  };

  if (!options.length) return null;

  return (
    <section data-market-explorer-rarity-markets className="py-2" aria-labelledby="rarity-markets-heading">
      <div className="flex items-center justify-between gap-2">
        <h3 id="rarity-markets-heading" className="text-xs font-semibold text-[var(--text-primary)]">Rarity Markets</h3>
        {activeCount ? <span className="text-[10px] font-semibold text-[rgb(45,212,191)]">{activeCount} active</span> : null}
      </div>
      <button type="button" data-rarity-market-trigger aria-expanded={open} aria-controls="rarity-market-options" onClick={() => setOpen((value) => !value)} className="mt-2 flex min-h-10 w-full items-center justify-between rounded-md border border-[var(--border-subtle)] px-3 text-left text-xs text-[var(--text-primary)]">
        <span>{activeCount ? `${activeCount} rarity market${activeCount === 1 ? "" : "s"} selected` : "Choose rarity markets"}</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div id="rarity-market-options" hidden={!open} className="mt-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/65 p-2">
        <label htmlFor="rarity-market-search" className="sr-only">Search rarities</label>
        <input
          id="rarity-market-search"
          data-rarity-market-search
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search all rarities…"
          className="mb-2 min-h-10 w-full rounded-md border border-[var(--border-subtle)] bg-transparent px-3 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(45,212,191)]"
        />
        <div className="max-h-72 space-y-1 overflow-y-auto pr-1" role="listbox" aria-label="All rarity markets">
          {filtered.map((option) => {
            const state = stateFor(option);
            const pending = pendingId === option.id;
            return (
              <button
                type="button"
                role="option"
                key={option.id}
                data-rarity-market={option.id}
                aria-selected={state.active}
                disabled={pending}
                onClick={() => toggle(option)}
                className={`flex w-full items-center justify-between gap-3 rounded-md border-l-2 px-2 py-2 text-left text-xs transition-colors hover:bg-white/[.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,.65)] ${state.active ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.12)] font-bold text-[rgb(45,212,191)]" : "border-transparent text-[var(--text-primary)]"}`}
              >
                <span className="min-w-0 truncate">{option.label}</span>
                <span className="flex-none text-[10px] font-semibold">{pending ? "Adding…" : state.active ? "Remove" : "+ Compare"}</span>
              </button>
            );
          })}
          {!filtered.length ? <p className="px-2 py-3 text-xs text-[var(--text-secondary)]">No matching rarity.</p> : null}
        </div>
        {message ? <p role="alert" className="mt-2 text-[10px] text-[var(--text-secondary)]">{message}</p> : null}
        <div className="mt-2 border-t border-[var(--border-subtle)] pt-2">
          <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Compare with</p>
          <div className="grid grid-cols-3 gap-1.5">
            <button type="button" onClick={() => openDirectory("sets")} className="rounded border border-[var(--border-subtle)] px-2 py-1.5 text-[10px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]">Set</button>
            <button type="button" onClick={() => openDirectory("eras")} className="rounded border border-[var(--border-subtle)] px-2 py-1.5 text-[10px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]">Era</button>
            <button type="button" onClick={() => openDirectory("quick")} className="rounded border border-[var(--border-subtle)] px-2 py-1.5 text-[10px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]">Quick Market</button>
          </div>
        </div>
      </div>
    </section>
  );
}
