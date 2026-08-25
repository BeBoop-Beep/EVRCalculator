"use client";

import { useEffect, useMemo, useState } from "react";
import {
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
  buildQueryLabel,
  normalizeQuerySpec,
} from "@/lib/explore/marketExplorerQuery.mjs";

const selectedValues = (event) => [...event.target.selectedOptions].map((option) => option.value);

function MultiSelect({ label, value, options, onChange, allLabel, name }) {
  return (
    <label className="min-w-0 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
      {label}
      <select
        data-market-query-control={name}
        multiple
        value={value}
        onChange={(event) => onChange(selectedValues(event))}
        className="mt-1 h-24 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-2 py-1 text-xs normal-case tracking-normal text-[var(--text-primary)]"
        aria-label={`${label}; no selection means ${allLabel}`}
      >
        {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select>
      <span className="mt-1 block font-normal normal-case tracking-normal">{value.length ? `${value.length} selected` : allLabel}</span>
    </label>
  );
}

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

  const availableSets = useMemo(() => {
    const all = Array.isArray(options?.sets) ? options.sets : [];
    return eraIds.length ? all.filter((entry) => eraIds.includes(entry.eraId)) : all;
  }, [options, eraIds]);
  useEffect(() => setSetIds((current) => current.filter((id) => availableSets.some((entry) => entry.id === id))), [availableSets]);

  const segments = Array.isArray(options?.segments?.segments) ? options.segments.segments : [];
  const spec = normalizeQuerySpec({ eraIds, setIds, segmentIds, mode, topN: mode === QUERY_MODE_CHASE ? 10 : null });
  const labels = {
    eraNames: Object.fromEntries((options?.eras || []).map((entry) => [entry.id, entry.label])),
    setNames: Object.fromEntries((options?.sets || []).map((entry) => [entry.id, entry.label])),
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
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-2 py-2 text-xs text-[var(--text-primary)]"><span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Asset</span>Cards</div>
            <MultiSelect label="Era" name="era" value={eraIds} options={options.eras || []} onChange={setEraIds} allLabel="All Eras" />
            <MultiSelect label="Set" name="set" value={setIds} options={availableSets} onChange={setSetIds} allLabel="All Sets" />
            <MultiSelect label="Card Segment / Rarity" name="segment" value={segmentIds} options={segments.map((entry) => ({ id: entry.key, label: entry.label }))} onChange={setSegmentIds} allLabel="All Rarities" />
            <label className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Mode
              <select data-market-query-control="mode" value={mode} onChange={(event) => setMode(event.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 px-2 py-2 text-xs normal-case tracking-normal text-[var(--text-primary)]">
                <option value={QUERY_MODE_ALL}>All Constituents</option><option value={QUERY_MODE_CHASE}>Chase</option>
              </select>
            </label>
            {mode === QUERY_MODE_CHASE ? <div data-market-query-top-n className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-2 py-2 text-xs text-[var(--text-primary)]"><span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Chase Size</span>Top 10</div> : null}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/25 px-3 py-2">
            <div className="min-w-0 flex-1"><span className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Query preview</span><p data-market-query-preview className="truncate text-xs font-semibold text-[var(--text-primary)]">{preview}</p></div>
            <button type="button" data-market-query-add disabled={loading} onClick={add} className="rounded-md bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{loading ? "Adding…" : "Add to Comparison"}</button>
          </div>
          {message ? <p role="status" className="mt-2 text-[11px] text-[var(--text-secondary)]">{message}</p> : null}
        </>
      )}
    </section>
  );
}
