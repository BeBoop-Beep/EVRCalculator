"use client";

import { useEffect, useMemo, useState } from "react";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import DarkSelect from "@/components/ui/DarkSelect";
import {
  MARKET_MODE_OPTIONS,
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
  buildQueryLabel,
  normalizeQuerySpec,
  sortEraOptions,
  sortSetOptions,
} from "@/lib/explore/marketExplorerQuery.mjs";

// The dynamic card-market builder.
//
// EVERY CONTROL IS AN inDex CONTROL. There is no `<select multiple>` here: the
// three filter axes are one shared MultiSelectFilter configured three ways, so
// the workspace never falls back to an OS-painted light dropdown, and Era, Set
// and Card Segment cannot drift apart visually or behaviourally.
//
// NO OPTION AUTHORITY LIVES HERE. Eras, sets and segments are whatever the
// authenticated options payload carried. This file only orders them
// canonically and narrows sets to the selected eras.

export default function MarketExplorerQueryBuilder({ onAddQuery }) {
  const [options, setOptions] = useState(null);
  const [eraIds, setEraIds] = useState([]);
  const [setIds, setSetIds] = useState([]);
  const [segmentIds, setSegmentIds] = useState([]);
  const [mode, setMode] = useState(QUERY_MODE_ALL);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let live = true;
    fetch("/api/market/explorer/query", { credentials: "include" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload?.message || "Unable to load query filters");
        if (live) setOptions(payload);
      })
      .catch((error) => { if (live) setMessage(error.message); });
    return () => { live = false; };
  }, []);

  // Canonical order, applied once. Rendering order is then a pure function of
  // the payload rather than of the order rows happened to arrive in.
  const eraOptions = useMemo(() => sortEraOptions(options?.eras), [options]);
  const allSetOptions = useMemo(() => sortSetOptions(options?.sets), [options]);
  const availableSets = useMemo(
    () => (eraIds.length ? allSetOptions.filter((entry) => eraIds.includes(entry.eraId)) : allSetOptions),
    [allSetOptions, eraIds]
  );
  // An era change can strand a set the user can no longer see. Reconciliation
  // drops it rather than leaving an impossible hidden selection in the spec.
  useEffect(() => setSetIds((current) => {
    const next = current.filter((id) => availableSets.some((entry) => entry.id === id));
    return next.length === current.length ? current : next;
  }), [availableSets]);

  const segments = useMemo(
    () => (Array.isArray(options?.segments?.segments) ? options.segments.segments : []),
    [options]
  );
  const segmentOptions = useMemo(
    () => segments.map((entry) => ({
      id: entry.key,
      label: entry.label,
      shortLabel: entry.shortLabel || entry.label,
      description: entry.definition || undefined,
      disabled: entry.available === false,
    })),
    [segments]
  );

  const spec = normalizeQuerySpec({ eraIds, setIds, segmentIds, mode, topN: mode === QUERY_MODE_CHASE ? 10 : null });
  const labels = {
    eraNames: Object.fromEntries(eraOptions.map((entry) => [entry.id, entry.label])),
    setNames: Object.fromEntries(allSetOptions.map((entry) => [entry.id, entry.label])),
    segmentNames: Object.fromEntries(segments.map((entry) => [entry.key, entry.label])),
  };
  const preview = buildQueryLabel(spec, labels);

  const add = async () => {
    setLoading(true);
    setMessage("");
    try {
      const outcome = await onAddQuery?.(spec);
      setMessage(outcome === "duplicate" ? "That market is already active." : "Added to comparison.");
    } catch (error) {
      setMessage(error?.message || "Unable to add this market.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section data-market-query-builder className="border-t border-[var(--border-subtle)] px-3 py-4 sm:px-4" aria-labelledby="market-query-builder-heading">
      <h3 id="market-query-builder-heading" className="text-sm font-semibold text-[var(--text-primary)]">Build a card market</h3>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">Filter the eligible universe first, then choose All Constituents or a global Top 10.</p>
      {!options ? <p role="status" className="mt-3 text-xs text-[var(--text-secondary)]">{message || "Loading canonical filters…"}</p> : (
        <>
          <div className="mt-3 grid grid-cols-1 gap-3 tab:grid-cols-2">
            <div className="min-w-0">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Asset</span>
              <p className="mt-1 flex min-h-11 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-2.5 py-1.5 text-xs text-[var(--text-primary)] desk:min-h-0">Cards</p>
            </div>

            {/* Era: a short, ordered list. Search would be pure furniture. */}
            <MultiSelectFilter
              label="Era"
              name="era"
              options={eraOptions}
              selectedIds={eraIds}
              onChange={setEraIds}
              allLabel="All Eras"
              summaryNoun="Eras"
              searchable={false}
              emptyMessage="No tracked eras."
            />

            {/* Set: the long axis, so it searches — client-side, over the
                canonical list already loaded. No request per keystroke. */}
            <MultiSelectFilter
              label="Set"
              name="set"
              options={availableSets}
              selectedIds={setIds}
              onChange={setSetIds}
              allLabel="All Sets"
              summaryNoun="Sets"
              searchable
              searchPlaceholder="Search sets…"
              emptyMessage="No tracked sets in the selected eras."
            />

            <MultiSelectFilter
              label="Card Segment / Rarity"
              name="segment"
              options={segmentOptions}
              selectedIds={segmentIds}
              onChange={setSegmentIds}
              allLabel="All Rarities"
              summaryNoun="segments"
              searchable={false}
              emptyMessage="No published card segments."
            />

            <div className="min-w-0">
              <span id="market-query-mode-label" className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Mode</span>
              <div className="mt-1 flex" data-market-query-control="mode" data-market-query-mode={mode}>
                <DarkSelect
                  ariaLabel="Market Mode"
                  value={mode}
                  onChange={setMode}
                  options={MARKET_MODE_OPTIONS.map((entry) => ({ value: entry.id, label: entry.label }))}
                />
              </div>
            </div>

            {mode === QUERY_MODE_CHASE ? (
              <div data-market-query-top-n className="min-w-0">
                <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Chase Size</span>
                <p className="mt-1 flex min-h-11 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-2.5 py-1.5 text-xs text-[var(--text-primary)] desk:min-h-0">Top 10</p>
              </div>
            ) : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2">
            <div className="min-w-0 flex-1">
              <span className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Query preview</span>
              <p data-market-query-preview className="truncate text-xs font-semibold text-[var(--text-primary)]">{preview}</p>
            </div>
            <button type="button" data-market-query-add disabled={loading} onClick={add} className="min-h-11 rounded-md bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50 desk:min-h-0">{loading ? "Adding…" : "Add to Comparison"}</button>
          </div>
          {message ? <p role="status" className="mt-2 text-[11px] text-[var(--text-secondary)]">{message}</p> : null}
        </>
      )}
    </section>
  );
}
