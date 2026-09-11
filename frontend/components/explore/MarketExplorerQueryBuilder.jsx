"use client";
import { useEffect, useMemo, useState } from "react";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import ExplorerDisclosure from "./ExplorerDisclosure";
import ExplorerMarketOption from "./ExplorerMarketOption";
import ExplorerSelectableRow from "./ExplorerSelectableRow";
import ExplorerPlanLockPanel from "./ExplorerPlanLockPanel";
import useMarketExplorerBuilderDraft from "@/hooks/explore/useMarketExplorerBuilderDraft";
import useMarketExplorerPreflight from "@/hooks/explore/useMarketExplorerPreflight";
import { PREFLIGHT_STATE, buildErrorMessage } from "@/lib/explore/marketExplorerPreflight.mjs";
import {
  QUERY_ASSET_CARDS,
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  QUERY_MEMBERSHIP_EXPLICIT,
  QUERY_MEMBERSHIP_FILTERS,
  buildQueryKey,
  presentationFor,
} from "@/lib/explore/marketExplorerQuery.mjs";
import { INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM } from "@/lib/access/indexPlanAccess.mjs";
import { planPresentation } from "@/lib/membership/upgradeFunnel.mjs";
import {
  OPTIONS_STATUS,
  backendMessage,
  resolveOptionsStatus,
} from "@/hooks/explore/useMarketExplorerFilterOptions";
import useMarketExplorerFilterOptions from "@/hooks/explore/useMarketExplorerFilterOptions";
import {
  MARKET_EXPLORER_SCREENS,
  MARKET_EXPLORER_QUICK_PRESETS,
  canUseScreen,
  draftForQuickPreset,
  resolveScreenResults,
} from "@/lib/explore/marketExplorerScreens.mjs";
export { OPTIONS_STATUS, backendMessage, resolveOptionsStatus };

function PreparedOptionList({ entries, onToggle, selectedSeriesCount }) {
  const isLocked = (entry) => entry.selected && selectedSeriesCount <= 1;
  return (
    <ul className="mt-1 space-y-1">
      {entries.map((entry) => (
        <li key={entry.key}>
          <ExplorerMarketOption
            entry={entry}
            onToggle={onToggle}
            isLocked={isLocked(entry)}
            lockReason={isLocked(entry) ? "Only market" : null}
          />
        </li>
      ))}
    </ul>
  );
}

export default function MarketExplorerQueryBuilder({
  options,
  optionsProvided = false,
  optionsStatus = "loading",
  optionsMessage = "",
  onRetryOptions,
  optionsRetrying = false,
  currentPlan = null,
  accessMode = "basic",
  coverageSummary = [],
  isAuthenticated = false,
  preparedSeries = [],
  activeSeries = [],
  benchmarkEntries = [],
  selectedSeriesCount = 0,
  onAddQuery,
  onUpdateQuery,
  editingSeries = null,
  onCancelEdit,
  onAddPrepared,
  onToggleBenchmark,
  preflightResult = null,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [buildStatus, setBuildStatus] = useState("idle");
  // Phase 5 moved these discovery surfaces into Compare / Analyze. Keeping
  // their old implementation unreachable during the migration protects the
  // frozen Phase-4 Builder mechanics while the new prepared-directory view
  // owns all screen interaction.
  const showLegacyAnalysis = false;
  const [selectedScreenId, setSelectedScreenId] = useState(null);
  const loadedOptions = useMarketExplorerFilterOptions({ enabled: !optionsProvided });
  const canonicalOptions = optionsProvided ? options : loadedOptions.options;
  const canonicalStatus = optionsProvided ? optionsStatus : loadedOptions.status;
  const canonicalMessage = optionsProvided ? optionsMessage : loadedOptions.message;
  const retryCanonicalOptions = optionsProvided ? onRetryOptions : loadedOptions.retry;
  const canonicalOptionsRetrying = optionsProvided ? optionsRetrying : loadedOptions.isRetrying;
  const builder = useMarketExplorerBuilderDraft({
    options: canonicalOptions,
    currentPlan,
    preparedSeries,
    activeSeries,
  });
  const { draft, spec, access, prepared, alreadyActive } = builder;
  const paid = currentPlan === "premium";
  const livePreflight = useMarketExplorerPreflight(spec, {
    enabled: !preflightResult && paid && Boolean(canonicalOptions) && Boolean(spec) && draft.asset === QUERY_ASSET_CARDS &&
      draft.membershipMode !== QUERY_MEMBERSHIP_EXPLICIT && !prepared && access.allowed,
  });
  const preflight = preflightResult || livePreflight;
  const knownEmpty = preflight.state === PREFLIGHT_STATE.empty;
  const editing = Boolean(editingSeries?.instanceId);
  const noChanges = Boolean(editing && spec && buildQueryKey(editingSeries.spec) === buildQueryKey(spec));
  useEffect(() => {
    if (!editingSeries?.spec) return;
    builder.replace({ ...editingSeries.spec, exactItems: editingSeries.exactItems || [] });
    setMobileOpen(true);
    setMessage("");
    // The instance id is the edit-session boundary. Draft field changes must
    // never reload the active result back over the user's unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingSeries?.instanceId]);
  const segmentOptions = builder.segments.map((entry) => ({
    id: entry.key,
    label: entry.label,
    shortLabel: entry.shortLabel || entry.label,
    description: entry.definition,
    disabled: entry.available === false,
  }));
  const pokemonOptions = builder.pokemonOptions.map((entry) => ({
    id: entry.id,
    label: entry.label,
    shortLabel: entry.label,
  }));
  const priceOptions = builder.priceSegments.map((entry) => ({
    id: entry.id,
    label: entry.label,
    description: entry.description,
  }));
  const releaseOptions = builder.releaseAgeCohorts.map((entry) => ({
    id: entry.id,
    label: entry.label,
    description: entry.description,
  }));
  const selectedScreen = MARKET_EXPLORER_SCREENS.find((entry) => entry.id === selectedScreenId) || null;
  const screenResults = useMemo(() => selectedScreen
    ? resolveScreenResults(selectedScreen, preparedSeries.filter((series) => series?.group === (draft.asset === QUERY_ASSET_CARDS ? "card" : "sealed")))
    : [], [selectedScreen, preparedSeries, draft.asset]);
  const selectedPresetId = useMemo(() => MARKET_EXPLORER_QUICK_PRESETS.find((preset) => {
    if (draft.asset !== "cards" || draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT) return false;
    const expected = draftForQuickPreset(preset, draft);
    return ["segmentIds", "pokemonIds", "priceSegmentIds", "releaseAgeCohortIds", "mode", "topN"]
      .every((key) => JSON.stringify(draft[key] ?? null) === JSON.stringify(expected[key] ?? null));
  })?.id || null, [draft]);
  const build = async (saveAsNew = false) => {
    if (!spec || (!editing && alreadyActive)) return;
    if (knownEmpty) {
      setMessage("No cards currently match these filters.");
      setBuildStatus("empty");
      return;
    }
    if (!prepared && !access.allowed) {
      setMessage(
        `This market requires Index ${access.requiredPlan === "premium" ? "Premium" : "Plus"}.`,
      );
      setBuildStatus("locked");
      return;
    }
    setLoading(true);
    setBuildStatus("building");
    setMessage("");
    try {
      const outcome = editing && !saveAsNew
        ? await onUpdateQuery?.(editingSeries.instanceId, spec, { exactItems: draft.exactItems })
        : prepared
          ? onAddPrepared?.(prepared.key)
          : await onAddQuery?.(spec, { exactItems: draft.exactItems });
      setMessage(
        outcome === "duplicate" ? "This market is already in the comparison." : outcome === "updated" ? "Market updated." : outcome === "unchanged" ? "No changes." : "Added to comparison.",
      );
      setBuildStatus("success");
      if (outcome !== "duplicate" && outcome !== "unchanged") {
        if (editing) onCancelEdit?.();
      }
    } catch (error) {
      setMessage(buildErrorMessage(error));
      setBuildStatus(error?.code || "error");
    } finally {
      setLoading(false);
    }
  };
  const accessPanel = (description) => (
    <ExplorerPlanLockPanel
      requiredPlan={INDEX_PLAN_PREMIUM}
      isAuthenticated={isAuthenticated}
      currentPlan={currentPlan}
      description={description}
    />
  );
  const assetControls = (asset) => {
    if (!paid)
      return accessPanel(
        asset === QUERY_ASSET_CARDS
          ? "Build card markets by Era, Set and Rarity with Index Plus."
          : "Build sealed markets by Era, Set and Product Family with Index Plus.",
      );
    if (!canonicalOptions) {
      if (canonicalStatus === OPTIONS_STATUS.forbidden) {
        return accessPanel("Your current plan does not include these protected Builder filters.");
      }
      const canRetry = canonicalStatus === OPTIONS_STATUS.unavailable || canonicalStatus === OPTIONS_STATUS.offline;
      return (
        <div
          role="status"
          data-market-query-options-state={canonicalStatus}
          className="mt-2 text-[11px] text-[var(--text-secondary)]"
        >
          <p>
            {canonicalStatus === OPTIONS_STATUS.loading
              ? "Loading canonical filters…"
              : canonicalStatus === OPTIONS_STATUS.offline
                ? "Unable to reach the market filter service. Check your connection and try again."
                : canonicalStatus === OPTIONS_STATUS.signedOut
                  ? "Your session is no longer authenticated. Sign in to continue."
                  : `The canonical market filters are temporarily unavailable.${canonicalMessage ? ` ${canonicalMessage}` : ""}`}
          </p>
          {canRetry && retryCanonicalOptions ? (
            <button
              type="button"
              data-market-query-options-retry
              disabled={canonicalOptionsRetrying}
              onClick={retryCanonicalOptions}
              className="mt-2 min-h-9 rounded-md border border-[var(--border-subtle)] px-3 font-semibold text-[var(--text-primary)] disabled:opacity-60"
            >
              {canonicalOptionsRetrying ? "Retrying filters…" : "Retry filters"}
            </button>
          ) : null}
        </div>
      );
    }
    if (draft.asset !== asset) return null;
    const presentation = presentationFor(asset);
    return (
      <div className="mt-2 space-y-2">
        <p className="px-1 pt-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Scope</p>
        <ExplorerDisclosure
          id={`${asset}EraSets`}
          title="Era & Set"
          summary={
            draft.eraIds.length || draft.setIds.length
              ? `${draft.eraIds.length + draft.setIds.length} selected`
              : "All"
          }
        >
          <div className="space-y-2">
            <MultiSelectFilter
              label="Era"
              name={`${asset}-era`}
              options={builder.eraOptions}
              selectedIds={draft.eraIds}
              onChange={builder.setEraIds}
              allLabel="All Eras"
              summaryNoun="Eras"
              searchable={false}
              emptyMessage="No tracked eras."
            />
            <MultiSelectFilter
              label="Set"
              name={`${asset}-set`}
              options={builder.visibleSets}
              selectedIds={draft.setIds}
              onChange={builder.setSetIds}
              allLabel="All Sets"
              summaryNoun="Sets"
              searchable
              searchPlaceholder="Search sets…"
              emptyMessage="No supported sets in the selected eras."
            />
          </div>
        </ExplorerDisclosure>
        <p className="px-1 pt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Filters</p>
        <ExplorerDisclosure
          id={`${asset}Segments`}
          title={asset === QUERY_ASSET_CARDS ? "Rarity" : "Product Family"}
          summary={
            draft.segmentIds.length
              ? `${draft.segmentIds.length} selected`
              : "All"
          }
        >
          <MultiSelectFilter
            key={asset}
            label={presentation.segmentLabel}
            name={`${asset}-segment`}
            options={segmentOptions}
            selectedIds={draft.segmentIds}
            onChange={builder.setSegmentIds}
            allLabel={presentation.allSegmentsLabel}
            summaryNoun={presentation.segmentSummaryNoun}
            searchable={asset === QUERY_ASSET_CARDS}
            searchPlaceholder={asset === QUERY_ASSET_CARDS ? "Search raritiesâ€¦" : undefined}
            emptyMessage={asset === QUERY_ASSET_CARDS ? "No filterable rarities." : "No published product families."}
          />
        </ExplorerDisclosure>
        {asset === QUERY_ASSET_CARDS ? (
          <ExplorerDisclosure id="cardsPokemon" title="Pokémon" badge="Premium">
            <MultiSelectFilter
              label="Pokémon"
              name="pokemon"
              options={pokemonOptions}
              selectedIds={draft.pokemonIds}
              onChange={builder.setPokemonIds}
              allLabel="All Pokémon"
              summaryNoun="Pokémon"
              searchable
              searchPlaceholder="Search Pokémon…"
              emptyMessage="No canonical Pokémon subjects."
            />
          </ExplorerDisclosure>
        ) : null}
        <ExplorerDisclosure
          id={`${asset}PriceSegments`}
          title="Price Segment"
          summary={
            draft.priceSegmentIds.length
              ? `${draft.priceSegmentIds.length} selected`
              : "All"
          }
        >
          <MultiSelectFilter
            label="Price Segment"
            name={`${asset}-price-segment`}
            options={priceOptions}
            selectedIds={draft.priceSegmentIds}
            onChange={builder.setPriceSegmentIds}
            allLabel="All Prices"
            summaryNoun="Price Segments"
            searchable={false}
            emptyMessage="No published price segments."
          />
        </ExplorerDisclosure>
        <ExplorerDisclosure
          id={`${asset}ReleaseAge`}
          title="Release Age"
          summary={
            draft.releaseAgeCohortIds.length
              ? `${draft.releaseAgeCohortIds.length} selected`
              : "All"
          }
        >
          <MultiSelectFilter
            label="Release Age"
            name={`${asset}-release-age`}
            options={releaseOptions}
            selectedIds={draft.releaseAgeCohortIds}
            onChange={builder.setReleaseAgeCohortIds}
            allLabel="All Release Ages"
            summaryNoun="Release Cohorts"
            searchable={false}
            emptyMessage="No published release cohorts."
          />
        </ExplorerDisclosure>
        {showLegacyAnalysis ? <><ExplorerDisclosure id={`${asset}Screens`} title="Screens" summary={selectedScreen?.asset === asset || selectedScreen?.asset == null ? selectedScreen?.label : null}>
          <p className="mb-2 text-[10px] leading-snug text-[var(--text-secondary)]">Pre-built market scans. Choose a Screen to see matching published markets, then add any result to the chart.</p>
          <div className="space-y-1">
            {MARKET_EXPLORER_SCREENS.filter((screen) => screen.asset === asset || screen.asset == null).map((screen) => {
              const unlocked = canUseScreen(screen, currentPlan);
              const lockTone = planPresentation(screen.requiredPlan === "premium" ? INDEX_PLAN_PREMIUM : INDEX_PLAN_PLUS);
              const selected = unlocked && selectedScreenId === screen.id;
              return <ExplorerSelectableRow key={screen.id} data-market-screen={screen.id}
                data-market-screen-locked={unlocked ? "false" : "true"}
                selected={selected}
                locked={!unlocked}
                onClick={() => {
                  if (!unlocked) return setMessage(`This Screen requires Index ${screen.requiredPlan === "premium" ? "Premium" : "Plus"}.`);
                  setSelectedScreenId(screen.id);
                  setMessage("");
                }}
                className={`min-h-11 w-full desk:min-h-0 ${!unlocked ? lockTone.compactClassName : ""}`}>
                <span className="block text-xs font-semibold text-[var(--text-primary)]">{screen.label}{unlocked ? "" : ` ðŸ”’ ${lockTone.label}`}</span>
                <span className="block text-[10px] text-[var(--text-secondary)]">{screen.description}</span>
              </ExplorerSelectableRow>;
            })}
          </div>
          {selectedScreen && (selectedScreen.asset === asset || selectedScreen.asset == null) && canUseScreen(selectedScreen, currentPlan) ? (
            <div data-market-screen-results className="mt-2 space-y-1">
              {screenResults.length ? screenResults.map((result, index) => (
                <button type="button" key={result.series.key} data-market-screen-result={result.series.key} data-market-screen-result-rank={index + 1} data-market-screen-result-metric={result.value}
                  aria-label={`${activeSeries.some((series) => series.key === result.series.key) ? "Active" : "Add"} ${result.series.shortLabel || result.series.label}`}
                  aria-current={activeSeries.some((series) => series.key === result.series.key) ? "true" : undefined}
                  onClick={() => activeSeries.some((series) => series.key === result.series.key) ? undefined : onAddPrepared?.(result.series.key)}
                  className="w-full rounded-md border border-[var(--border-subtle)] px-2 py-2 text-left text-[11px] text-[var(--text-primary)]">
                  {index + 1}. {result.series.shortLabel || result.series.label} <span className="text-[var(--text-secondary)]">{result.value.toFixed(1)}%</span>
                  <strong className="float-right text-[rgb(45,212,191)]">{activeSeries.some((series) => series.key === result.series.key) ? "Active" : "Add"}</strong>
                </button>
              )) : (
                <p role="status" className="rounded-md border border-[var(--border-subtle)] px-2 py-2 text-[11px] text-[var(--text-secondary)]">
                  No prepared markets currently qualify for this Screen.
                </p>
              )}
            </div>
          ) : null}
        </ExplorerDisclosure>
        {asset === QUERY_ASSET_CARDS ? <ExplorerDisclosure id="cardsQuickPresets" title="Quick Presets" summary={MARKET_EXPLORER_QUICK_PRESETS.find((preset) => preset.id === selectedPresetId)?.label || null}>
          <p className="mb-2 text-[10px] leading-snug text-[var(--text-secondary)]">One-click Builder setups. Apply a preset, adjust filters if you want, then Build Market.</p>
          <div className="space-y-1">{MARKET_EXPLORER_QUICK_PRESETS.map((preset) => <button type="button" key={preset.id} data-market-preset={preset.id} aria-pressed={selectedPresetId === preset.id} onClick={() => {
            if (!canUseScreen(preset, currentPlan)) { setBuildStatus("locked"); setMessage(`This preset requires Index ${preset.requiredPlan === "premium" ? "Premium" : "Plus"}.`); return; }
            if (preset.id === "set-top-ten" && draft.setIds.length !== 1) { setBuildStatus("error"); setMessage(draft.setIds.length ? "Choose exactly one set." : "Choose one set first."); return; }
            builder.replace(draftForQuickPreset(preset, draft)); setBuildStatus("idle"); setMessage("");
          }} className={`w-full rounded-md border px-3 py-2 text-left text-xs ${selectedPresetId === preset.id ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)]" : "border-[var(--border-subtle)]"}`}><strong className="block">{preset.label}</strong><span className="text-[10px] text-[var(--text-secondary)]">{preset.description}</span></button>)}</div>
        </ExplorerDisclosure> : null}</> : null}
        {asset === QUERY_ASSET_CARDS ? (
          <ExplorerDisclosure id="cardsReference" title="Reference Market">
            {paid ? <PreparedOptionList entries={benchmarkEntries} onToggle={onToggleBenchmark} selectedSeriesCount={selectedSeriesCount} /> : accessPanel("Add the Per-Set Chase reference market with Index Plus.")}
          </ExplorerDisclosure>
        ) : null}
      </div>
    );
  };
  const body = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        data-market-builder-scroll-region
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-3 sm:px-4"
      >
        <ExplorerDisclosure id="rawCardsBuilder" title="Raw Cards" open={draft.asset === QUERY_ASSET_CARDS} onToggle={() => { builder.setAsset(QUERY_ASSET_CARDS); setSelectedScreenId(null); setMessage(""); }} summary={draft.asset === QUERY_ASSET_CARDS ? "Editing" : null}>
          {assetControls(QUERY_ASSET_CARDS)}
        </ExplorerDisclosure>
        <ExplorerDisclosure id="sealedBuilder" title="Sealed" open={draft.asset === QUERY_ASSET_SEALED} onToggle={() => { builder.setAsset(QUERY_ASSET_SEALED); setSelectedScreenId(null); setMessage(""); }} summary={draft.asset === QUERY_ASSET_SEALED ? "Editing" : null}>
          {assetControls(QUERY_ASSET_SEALED)}
        </ExplorerDisclosure>
        <ExplorerDisclosure
          id="gradedBuilder"
          title="Graded"
          badge="Unavailable"
        >
          <p className="text-[11px] text-[var(--text-secondary)]">
            No authoritative graded market is published.
          </p>
        </ExplorerDisclosure>
        <ExplorerDisclosure id="myMarkets" title="My Markets" badge="Foundation">
          <div data-market-personal-foundation className="space-y-2">
            <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
              <p className="text-xs font-semibold text-[var(--text-primary)]">Portfolio</p>
              <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-secondary)]">
                Total, Raw, Sealed, and Graded collection value comparisons are being prepared. Value history is not Market Index performance.
              </p>
            </div>
            <div aria-disabled="true" className="px-3 py-1 opacity-70">
              <p className="text-xs font-semibold text-[var(--text-secondary)]">Wishlist · Unavailable</p>
              <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-secondary)]">
                Wishlist market history becomes available once saved Wishlist membership is published.
              </p>
            </div>
          </div>
        </ExplorerDisclosure>
        {false ? <ExplorerDisclosure id="benchmarks" title="Benchmarks">
          {paid ? (
            <PreparedOptionList
              entries={benchmarkEntries}
              onToggle={onToggleBenchmark}
              selectedSeriesCount={selectedSeriesCount}
            />
          ) : (
            accessPanel("Add prepared comparison benchmarks with Index Plus.")
          )}
        </ExplorerDisclosure> : null}
      </div>
      <div
        data-current-market
        data-market-builder-editing={editing ? "true" : "false"}
        className="sticky bottom-0 border-t border-[var(--border-subtle)] bg-[var(--surface-page)]/95 px-3 py-3 backdrop-blur sm:px-4"
      >
        <p className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
          {editing ? "Unsaved edits" : "Current Market"}
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          {editing ? `Editing: ${editingSeries.shortLabel || editingSeries.label}` : draft.asset === QUERY_ASSET_SEALED ? "Sealed" : "Raw Cards"}
        </p>
        {editing && !noChanges ? <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[rgb(251,191,36)]">Unsaved changes · active line unchanged</p> : null}
        <p
          data-current-market-preview
          className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)]"
        >
          {builder.preview}
        </p>
        {preflight.message ? <p data-market-builder-preflight={preflight.state} role="status" className="mt-1 text-[11px] text-[var(--text-secondary)]">{preflight.message}</p> : null}
        {!prepared && !access.allowed ? (
          <p
            data-current-market-lock
            className={`mt-2 rounded-md border px-2 py-1 text-[11px] ${planPresentation(INDEX_PLAN_PREMIUM).compactClassName}`}
          >
            🔒 Index Premium — combining dimensions or custom ranking requires
            Index Premium.
          </p>
        ) : null}
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            data-market-builder-clear
            onClick={() => { if (editing) onCancelEdit?.(); else builder.clear(); setMessage(""); }}
            className="min-h-11 rounded-md border border-[var(--border-subtle)] px-3 text-xs font-semibold text-[var(--text-secondary)] desk:min-h-0"
          >
            {editing ? "Cancel" : "Clear"}
          </button>
          <button
            type="button"
            data-market-builder-build
            onClick={() => build(false)}
            disabled={loading || !spec || knownEmpty || noChanges || (!editing && alreadyActive) || (!prepared && !access.allowed)}
            className="min-h-11 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-3 text-xs font-semibold text-[rgb(45,212,191)] disabled:opacity-50 desk:min-h-0"
          >
            {noChanges ? "No changes" : !editing && alreadyActive
              ? "Already Active"
              : loading
                ? "Building…"
                : !prepared && !access.allowed
                  ? "Build Market 🔒"
                  : editing ? "Update Market" : "Build Market"}
          </button>
        </div>
        {editing && !noChanges ? (
          <button type="button" data-market-builder-save-as-new disabled={loading || !spec || (!prepared && !access.allowed)} onClick={() => build(true)} className="mt-2 min-h-11 w-full rounded-md border border-[var(--border-subtle)] px-3 text-xs font-semibold text-[var(--text-secondary)]">
            Save as new
          </button>
        ) : null}
        {message ? (
          <p
            role={buildStatus === "error" ? "alert" : "status"}
            className={`mt-2 rounded-md border px-2 py-1 text-[11px] ${buildStatus === "error" ? "border-red-400/40 text-red-200" : "border-transparent text-[var(--text-secondary)]"}`}
          >
            {message}
          </p>
        ) : null}
      </div>
    </div>
  );
  return (<>
    <section
      data-market-explorer-filters
      data-market-builder-asset={draft.asset}
      className="flex min-w-0 flex-col desk:max-h-[42rem]"
      aria-labelledby="market-builder-heading"
    >
      <div className="flex items-start gap-2 border-b border-[var(--border-subtle)] px-3 py-3 sm:px-4">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-[rgb(45,212,191)]">inDex</p>
          <div className="flex flex-wrap items-center gap-2">
          <h2
            id="market-builder-heading"
            className="text-[16px] font-semibold text-[var(--text-primary)]"
          >
            Market Explorer
          </h2>
          <span data-market-explorer-plan-badge data-market-explorer-plan={accessMode} className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">{accessMode === "premium" ? "Index Premium" : accessMode === "plus" ? "Index Plus" : "Basic"}</span>
          </div>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            Build, compare, and inspect markets.
          </p>
          {coverageSummary.length ? <p data-market-coverage-summary className="mt-1 text-[9px] leading-tight text-[var(--text-secondary)]">{coverageSummary.join(" · ")}</p> : null}
        </div>
        <button
          type="button"
          data-market-builder-mobile-toggle
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((value) => !value)}
          className="ml-auto rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-semibold text-[var(--text-secondary)] desk:hidden"
        >
          {mobileOpen ? "Hide" : "Build"}
        </button>
      </div>
      <div
        className={
          mobileOpen
            ? "flex min-h-0 flex-1 flex-col"
            : "hidden min-h-0 flex-1 flex-col desk:flex"
        }
      >
        {body}
      </div>
    </section>
  </>);
}
