"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useMarketExplorerFilterOptions, {
  OPTIONS_STATUS,
  backendMessage,
  resolveOptionsStatus,
} from "@/hooks/explore/useMarketExplorerFilterOptions";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import DarkSelect from "@/components/ui/DarkSelect";
import {
  QUERY_ASSET_CARDS,
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
  buildQueryLabel,
  marketModeOptions,
  normalizeQuerySpec,
  presentationFor,
  sortEraOptions,
  sortSetOptions,
} from "@/lib/explore/marketExplorerQuery.mjs";

// The dynamic market builder — Cards AND Sealed Products.
//
// ONE BUILDER, ONE STATE MODEL. The asset selects which segment vocabulary and
// which mode wording apply; it does NOT select a different component. Era, Set,
// Market Mode and the preview are literally the same controls for both assets,
// so the two workflows cannot drift apart. Changing asset resets only the
// segment selection, because a card rarity is not a sealed family and carrying
// one across would describe no market at all.
//
// EVERY CONTROL IS AN inDex CONTROL. There is no `<select multiple>` here: the
// filter axes are one shared MultiSelectFilter configured per axis.
//
// NO OPTION AUTHORITY LIVES HERE. Eras, sets, rarities and product families are
// whatever the authenticated options payload carried. This file only orders
// them canonically and narrows sets to the selected eras and asset.

// The option-loading vocabulary now lives with the shared hook, because Era &
// Sets loads the SAME payload and both surfaces must classify a 401 the same
// way. Re-exported here so the existing contract tests and any other importer
// keep their import site.
export { OPTIONS_STATUS, backendMessage, resolveOptionsStatus };

function OptionsState({ status, message }) {
  if (status === OPTIONS_STATUS.signedOut) {
    return (
      <div data-market-query-options-state="signedOut" className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-3 py-3">
        <p className="text-xs text-[var(--text-primary)]">Sign in to build a custom market.</p>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          Prepared segments above stay available to everyone.
        </p>
        <Link
          href="/login"
          data-market-query-sign-in
          className="mt-2 inline-flex min-h-11 items-center rounded-md bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-white desk:min-h-0"
        >
          Sign in
        </Link>
      </div>
    );
  }
  if (status === OPTIONS_STATUS.offline || status === OPTIONS_STATUS.unavailable) {
    return (
      <p role="status" data-market-query-options-state={status} className="mt-3 text-xs text-[var(--text-secondary)]">
        The market query service is temporarily unavailable.{message ? ` ${message}` : ""}
      </p>
    );
  }
  return (
    <p role="status" data-market-query-options-state="loading" className="mt-3 text-xs text-[var(--text-secondary)]">
      Loading canonical filters…
    </p>
  );
}

export default function MarketExplorerQueryBuilder({ onAddQuery, scopeHandoff = null }) {
  // ONE canonical options request for the page: Era & Sets reads the same
  // payload through the same hook, so the two surfaces can never disagree
  // about which eras and sets exist.
  const { status: optionsStatus, options, message: optionsMessage } = useMarketExplorerFilterOptions();
  const [asset, setAsset] = useState(QUERY_ASSET_CARDS);
  const [eraIds, setEraIds] = useState([]);
  const [setIds, setSetIds] = useState([]);
  const [segmentIds, setSegmentIds] = useState([]);
  const [mode, setMode] = useState(QUERY_MODE_ALL);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  // WHY A STATUS AND NOT ONE MESSAGE STRING. Every cause used to collapse into
  // "Unable to load query filters": FastAPI answers 401 with `detail`, not
  // `message`, so a signed-out user — the overwhelmingly common case — was told
  // the filters were broken. The cause is carried explicitly, because "sign in"
  // and "the service is down" call for different actions.

  // The Era & Sets hand-off. It fires ONLY when the user pressed "Use in Build
  // a Market"; the two controls are otherwise independent, and neither rewrites
  // the other's state on its own. `token` changes per press, so asking twice
  // re-applies rather than being swallowed as an unchanged value.
  useEffect(() => {
    if (!scopeHandoff) return;
    setEraIds(scopeHandoff.eraIds || []);
    setSetIds(scopeHandoff.setIds || []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeHandoff?.token]);

  const presentation = presentationFor(asset);

  // Canonical order, applied once. Rendering order is then a pure function of
  // the payload rather than of the order rows happened to arrive in.
  const eraOptions = useMemo(() => sortEraOptions(options?.eras), [options]);
  // A set with no prepared sealed snapshot has no sealed market to offer. The
  // backend states which assets each set supports; a set that predates the flag
  // is assumed to support cards, which is the historical contract.
  const allSetOptions = useMemo(() => sortSetOptions(options?.sets).filter(
    (entry) => (Array.isArray(entry.assets) ? entry.assets.includes(asset) : asset === QUERY_ASSET_CARDS)
  ), [options, asset]);
  const availableSets = useMemo(
    () => (eraIds.length ? allSetOptions.filter((entry) => eraIds.includes(entry.eraId)) : allSetOptions),
    [allSetOptions, eraIds]
  );
  // An era or asset change can strand a set the user can no longer see.
  // Reconciliation drops it rather than leaving an impossible hidden selection.
  useEffect(() => setSetIds((current) => {
    const next = current.filter((id) => availableSets.some((entry) => entry.id === id));
    return next.length === current.length ? current : next;
  }), [availableSets]);

  // Each asset reads its OWN vocabulary. `segments` remains the card taxonomy's
  // published key for backward compatibility with the existing contract.
  const segments = useMemo(() => {
    if (asset === QUERY_ASSET_SEALED) {
      return Array.isArray(options?.sealedProductFamilies?.segments)
        ? options.sealedProductFamilies.segments : [];
    }
    const cards = options?.cardSegments?.segments || options?.segments?.segments;
    return Array.isArray(cards) ? cards : [];
  }, [options, asset]);
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
  // A card rarity is not a sealed family. Switching asset must clear the
  // segment selection rather than carry a key the new asset would reject.
  useEffect(() => setSegmentIds([]), [asset]);

  const modeOptions = useMemo(() => marketModeOptions(asset), [asset]);
  const spec = normalizeQuerySpec({ asset, eraIds, setIds, segmentIds, mode, topN: mode === QUERY_MODE_CHASE ? 10 : null });
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
    <section data-market-query-builder className="pt-1" aria-labelledby="market-query-builder-heading">
      {/* The heading names the ADVANCED LANE, and the copy states how it
          differs from Explore Segments: prepared vs custom. */}
      <h3 id="market-query-builder-heading" className="text-sm font-semibold text-[var(--text-primary)]">Build a Market</h3>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        Create a custom filtered market. Choose an asset, narrow the eligible universe by era, set and segment, then
        rank it. A Top 10 market is charted alongside the same filtered universe in All mode, because that is the only
        benchmark that can interpret it.
      </p>
      {!options ? <OptionsState status={optionsStatus} message={optionsMessage} /> : (
        <>
          <div className="mt-3 grid grid-cols-1 gap-3 tab:grid-cols-2">
            {/* Asset first: it decides the segment vocabulary and the mode
                wording for every control below it. */}
            <div className="min-w-0">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Asset</span>
              <div className="mt-1 flex" data-market-query-control="asset" data-market-query-asset={asset}>
                <DarkSelect
                  ariaLabel="Asset"
                  value={asset}
                  onChange={setAsset}
                  options={[
                    { value: QUERY_ASSET_CARDS, label: "Cards" },
                    { value: QUERY_ASSET_SEALED, label: "Sealed Products" },
                  ]}
                />
              </div>
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

            {/* ONE control, named by the asset. `key` forces a fresh control
                per asset so no popover state survives a vocabulary change. */}
            <MultiSelectFilter
              key={`segment-${asset}`}
              label={presentation.segmentLabel}
              name="segment"
              options={segmentOptions}
              selectedIds={segmentIds}
              onChange={setSegmentIds}
              allLabel={presentation.allSegmentsLabel}
              summaryNoun={presentation.segmentSummaryNoun}
              searchable={false}
              emptyMessage={asset === QUERY_ASSET_SEALED
                ? "No published sealed product families."
                : "No published card segments."}
            />

            <div className="min-w-0">
              <span id="market-query-mode-label" className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Mode</span>
              <div className="mt-1 flex" data-market-query-control="mode" data-market-query-mode={mode}>
                <DarkSelect
                  ariaLabel="Market Mode"
                  value={mode}
                  onChange={setMode}
                  options={modeOptions.map((entry) => ({ value: entry.id, label: entry.label }))}
                />
              </div>
            </div>

            {mode === QUERY_MODE_CHASE ? (
              <div data-market-query-top-n className="min-w-0">
                <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  {asset === QUERY_ASSET_SEALED ? "Basket Size" : "Chase Size"}
                </span>
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
