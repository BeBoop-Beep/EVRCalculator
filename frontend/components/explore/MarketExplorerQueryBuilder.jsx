"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import DarkSelect from "@/components/ui/DarkSelect";
import ExplorerDisclosure from "./ExplorerDisclosure";
import ExplorerMarketOption from "./ExplorerMarketOption";
import ExplorerPlanLockPanel from "./ExplorerPlanLockPanel";
import MarketExplorerExactItemPicker from "./MarketExplorerExactItemPicker";
import useMarketExplorerBuilderDraft from "@/hooks/explore/useMarketExplorerBuilderDraft";
import {
  QUERY_ASSET_CARDS,
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
  QUERY_MEMBERSHIP_EXPLICIT,
  QUERY_MEMBERSHIP_FILTERS,
  buildQueryKey,
  marketModeOptions,
  presentationFor,
} from "@/lib/explore/marketExplorerQuery.mjs";
import {
  INDEX_PLAN_PLUS,
  INDEX_PLAN_PREMIUM,
} from "@/lib/access/indexPlanAccess.mjs";
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
  draftForScreenResult,
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
  optionsStatus = "loading",
  optionsMessage = "",
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
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [buildStatus, setBuildStatus] = useState("idle");
  const [exactOpen, setExactOpen] = useState(false);
  const exactTriggerRef = useRef(null);
  const [selectedScreenId, setSelectedScreenId] = useState(null);
  const loadedOptions = useMarketExplorerFilterOptions({ enabled: options === undefined });
  const canonicalOptions = options || loadedOptions.options;
  const canonicalStatus = options ? optionsStatus : loadedOptions.status;
  const canonicalMessage = options ? optionsMessage : loadedOptions.message;
  const builder = useMarketExplorerBuilderDraft({
    options: canonicalOptions,
    currentPlan,
    preparedSeries,
    activeSeries,
  });
  const { draft, spec, access, prepared, alreadyActive } = builder;
  const editing = Boolean(editingSeries?.instanceId);
  const noChanges = Boolean(editing && spec && buildQueryKey(editingSeries.spec) === buildQueryKey(spec));
  useEffect(() => {
    if (!editingSeries?.spec) return;
    builder.replace({ ...editingSeries.spec, exactItems: editingSeries.exactItems || [] });
    setMobileOpen(true);
    if (editingSeries.spec.membershipMode === QUERY_MEMBERSHIP_EXPLICIT) setExactOpen(true);
    setMessage("");
    // The instance id is the edit-session boundary. Draft field changes must
    // never reload the active result back over the user's unsaved edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingSeries?.instanceId]);
  const paid = currentPlan === "plus" || currentPlan === "premium";
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
  const selectedScreen =
    MARKET_EXPLORER_SCREENS.find((entry) => entry.id === selectedScreenId) ||
    null;
  const screenResults = useMemo(
    () =>
      selectedScreen
        ? resolveScreenResults(selectedScreen, preparedSeries.filter((series) =>
            series?.group === (draft.asset === QUERY_ASSET_CARDS ? "card" : "sealed")
          ))
        : [],
    [selectedScreen, preparedSeries, draft.asset],
  );
  const selectedPresetId = useMemo(() => MARKET_EXPLORER_QUICK_PRESETS.find((preset) => {
    if (draft.asset !== "cards" || draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT) return false;
    const expected = draftForScreenResult(preset, null, draft);
    return ["segmentIds", "pokemonIds", "priceSegmentIds", "releaseAgeCohortIds", "mode", "topN"]
      .every((key) => JSON.stringify(draft[key] ?? null) === JSON.stringify(expected[key] ?? null));
  })?.id || null, [draft]);
  const narrowingSummary = useMemo(() => [
    draft.eraIds.length ? `${draft.eraIds.length} era${draft.eraIds.length === 1 ? "" : "s"}` : null,
    draft.setIds.length ? `${draft.setIds.length} set${draft.setIds.length === 1 ? "" : "s"}` : null,
    draft.segmentIds.length ? `${draft.segmentIds.length} ${draft.asset === "cards" ? "rarity" : "family"} filter${draft.segmentIds.length === 1 ? "" : "s"}` : null,
    draft.pokemonIds.length ? `${draft.pokemonIds.length} Pokémon` : null,
    draft.priceSegmentIds.length ? `${draft.priceSegmentIds.length} price filter${draft.priceSegmentIds.length === 1 ? "" : "s"}` : null,
    draft.releaseAgeCohortIds.length ? `${draft.releaseAgeCohortIds.length} release filter${draft.releaseAgeCohortIds.length === 1 ? "" : "s"}` : null,
  ].filter(Boolean), [draft]);
  const build = async (saveAsNew = false) => {
    if (!spec || (!editing && alreadyActive)) return;
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
      setExactOpen(false);
      if (outcome === "updated") onCancelEdit?.();
    } catch (error) {
      setMessage(
        error?.message ||
          "The market query service is temporarily unavailable.",
      );
      setBuildStatus("error");
    } finally {
      setLoading(false);
    }
  };
  const accessPanel = (description) => (
    <ExplorerPlanLockPanel
      requiredPlan={INDEX_PLAN_PLUS}
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
    if (!canonicalOptions)
      return (
        <p
          role="status"
          className="mt-2 text-[11px] text-[var(--text-secondary)]"
        >
          {canonicalStatus === "loading"
            ? "Loading canonical filters…"
            : canonicalMessage ||
              "The canonical market filters are temporarily unavailable."}
        </p>
      );
    if (draft.asset !== asset) return null;
    const presentation = presentationFor(asset);
    return (
      <div className="mt-2 space-y-2">
        <div data-market-builder-membership-mode role="radiogroup" aria-label="Build from" className="grid grid-cols-2 gap-2">
          <button type="button" role="radio" aria-checked={draft.membershipMode !== QUERY_MEMBERSHIP_EXPLICIT} onClick={() => builder.setMembershipMode(QUERY_MEMBERSHIP_FILTERS)} className={`min-h-10 rounded-md border px-2 text-xs font-semibold ${draft.membershipMode !== QUERY_MEMBERSHIP_EXPLICIT ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>Filters</button>
          <button ref={exactTriggerRef} type="button" role="radio" aria-checked={draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT} onClick={() => { builder.setMembershipMode(QUERY_MEMBERSHIP_EXPLICIT); setExactOpen(true); setBuildStatus("idle"); setMessage(""); }} className={`min-h-10 rounded-md border px-2 text-xs font-semibold ${draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.14)] text-[rgb(45,212,191)]" : "border-[var(--border-subtle)] text-[var(--text-secondary)]"}`}>Exact Items <span className="text-[9px] opacity-75">Premium</span></button>
        </div>
        {draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT ? <button type="button" data-market-exact-open onClick={() => setExactOpen(true)} className="w-full rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-left text-xs"><strong className="block text-[var(--text-primary)]">Exact Items</strong><span className="text-[var(--text-secondary)]">{draft.exactItems?.length || 0} selected · Open selection workspace</span></button> : null}
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
            searchable={false}
            emptyMessage="No published segment options."
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
        <ExplorerDisclosure
          id={`${asset}Composition`}
          title="Composition"
          summary={draft.mode === QUERY_MODE_CHASE ? `Top ${draft.topN || 10}` : "All"}
        >
          <DarkSelect
            ariaLabel="Market Mode"
            value={draft.mode}
            onChange={builder.setMode}
            options={marketModeOptions(asset).map((entry) => ({
              value: entry.id,
              label: asset === QUERY_ASSET_SEALED && entry.id === QUERY_MODE_CHASE ? "Top N by Price" : entry.label,
            }))}
          />
          <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
            {asset === QUERY_ASSET_SEALED ? "All Products or the highest-priced products in this scope." : "All Cards or a Top N chase composition in this scope."}
          </p>
        </ExplorerDisclosure>
        <ExplorerDisclosure id={`${asset}Screens`} title="Screens" summary={selectedScreen?.asset === asset || selectedScreen?.asset == null ? selectedScreen?.label : null}>
          <p className="mb-2 text-[10px] leading-snug text-[var(--text-secondary)]">Pre-built market scans. Choose a Screen to see matching published markets, then add any result to the chart.</p>
          <div className="space-y-1">
            {MARKET_EXPLORER_SCREENS.filter((screen) => screen.asset === asset || screen.asset == null).map((screen) => {
              const unlocked = canUseScreen(screen, currentPlan);
              const lockTone = planPresentation(screen.requiredPlan === "premium" ? INDEX_PLAN_PREMIUM : INDEX_PLAN_PLUS);
              return <button type="button" key={screen.id} data-market-screen={screen.id}
                data-market-screen-locked={unlocked ? "false" : "true"}
                aria-pressed={selectedScreenId === screen.id}
                onClick={() => {
                  if (!unlocked) return setMessage(`This Screen requires Index ${screen.requiredPlan === "premium" ? "Premium" : "Plus"}.`);
                  setSelectedScreenId(screen.id);
                  setMessage("");
                }}
                className={`min-h-11 w-full rounded-md border px-3 text-left focus-visible:outline-none focus-visible:ring-2 desk:min-h-0 ${selectedScreenId === screen.id ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)]" : unlocked ? "border-[var(--border-subtle)]" : lockTone.compactClassName}`}>
                {selectedScreenId === screen.id ? <span aria-hidden="true" className="float-right text-[rgb(45,212,191)]">✓</span> : null}
                <span className="block text-xs font-semibold text-[var(--text-primary)]">{screen.label}{unlocked ? "" : ` ðŸ”’ ${lockTone.label}`}</span>
                <span className="block text-[10px] text-[var(--text-secondary)]">{screen.description}</span>
              </button>;
            })}
          </div>
          {selectedScreen && (selectedScreen.asset === asset || selectedScreen.asset == null) && canUseScreen(selectedScreen, currentPlan) ? (
            <div data-market-screen-results className="mt-2 space-y-1">
              {screenResults.length ? screenResults.map((result, index) => (
                <button type="button" key={result.series.key} data-market-screen-result={result.series.key}
                  aria-label={`${activeSeries.some((series) => series.key === result.series.key) ? "Active" : "Add"} ${result.series.shortLabel || result.series.label}`}
                  disabled={activeSeries.some((series) => series.key === result.series.key)}
                  onClick={() => onAddPrepared?.(result.series.key)}
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
            builder.replace(draftForScreenResult(preset, null, draft)); setBuildStatus("idle"); setMessage("");
          }} className={`w-full rounded-md border px-3 py-2 text-left text-xs ${selectedPresetId === preset.id ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,.14)]" : "border-[var(--border-subtle)]"}`}><strong className="block">{preset.label}</strong><span className="text-[10px] text-[var(--text-secondary)]">{preset.description}</span></button>)}</div>
        </ExplorerDisclosure> : null}
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
        {false ? <ExplorerDisclosure id="screens" title="Screens">
          <div className="space-y-1">
            {MARKET_EXPLORER_SCREENS.map((screen) => {
              const unlocked = canUseScreen(screen, currentPlan);
              const lockTone = planPresentation(
                screen.requiredPlan === "premium"
                  ? INDEX_PLAN_PREMIUM
                  : INDEX_PLAN_PLUS,
              );
              return (
                <button
                  type="button"
                  key={screen.id}
                  data-market-screen={screen.id}
                  data-market-screen-locked={unlocked ? "false" : "true"}
                  onClick={() =>
                    unlocked
                      ? setSelectedScreenId(screen.id)
                      : setMessage(
                          `This Screen requires Index ${screen.requiredPlan === "premium" ? "Premium" : "Plus"}.`,
                        )
                  }
                  className={`min-h-11 w-full rounded-md border px-3 text-left focus-visible:outline-none focus-visible:ring-2 desk:min-h-0 ${unlocked ? "border-[var(--border-subtle)]" : lockTone.compactClassName}`}
                >
                  <span className="block text-xs font-semibold text-[var(--text-primary)]">
                    {screen.label}
                    {unlocked ? "" : ` 🔒 ${lockTone.label}`}
                  </span>
                  <span className="block text-[10px] text-[var(--text-secondary)]">
                    {screen.description}
                  </span>
                </button>
              );
            })}
          </div>
          {selectedScreen && canUseScreen(selectedScreen, currentPlan) ? (
            <div data-market-screen-results className="mt-2 space-y-1">
              {screenResults.length ? (
                screenResults.map((result, index) => (
                  <button
                    type="button"
                    key={result.series.key}
                    onClick={() => {
                      builder.replace(
                        draftForScreenResult(selectedScreen, result, draft),
                      );
                      onAddPrepared?.(result.series.key);
                    }}
                    className="w-full rounded-md border border-[var(--border-subtle)] px-2 py-2 text-left text-[11px] text-[var(--text-primary)]"
                  >
                    {index + 1}.{" "}
                    {result.series.shortLabel || result.series.label}{" "}
                    <span className="text-[var(--text-secondary)]">
                      {result.value.toFixed(1)}%
                    </span>
                  </button>
                ))
              ) : selectedScreen.id === "set-top-ten" && draft.setIds.length === 0 ? (
                // "Top 10 in Selected Set" is meaningless with no set: an empty
                // setIds resolves to "every eligible set" (the canonical
                // EMPTY-MEANS-ALL rule), silently turning this screen into a
                // plain Global Top 10 -- a different market the user did not
                // ask for. Require the set explicitly rather than guess it.
                <p
                  data-market-screen-requires-set
                  className="rounded-md border border-[var(--border-subtle)] px-2 py-2 text-[11px] text-[var(--text-secondary)]"
                >
                  Select one set under Raw Cards → Era &amp; Set first, then apply this screen.
                </p>
              ) : (
                <button
                  type="button"
                  data-market-screen-apply={selectedScreen.id}
                  onClick={() =>
                    builder.replace(
                      draftForScreenResult(selectedScreen, null, draft),
                    )
                  }
                  className="w-full rounded-md border border-[var(--border-subtle)] px-2 py-2 text-left text-[11px] text-[var(--text-primary)]"
                >
                  Legacy handoff removed
                </button>
              )}
            </div>
          ) : null}
        </ExplorerDisclosure> : null}
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
        {false && paid ? (
          <ExplorerDisclosure
            id="marketComposition"
            title="Composition"
            summary={draft.mode === QUERY_MODE_CHASE ? "Top 10" : "All"}
          >
            <DarkSelect
              ariaLabel="Market Mode"
              value={draft.mode}
              onChange={builder.setMode}
              options={marketModeOptions(draft.asset).map((entry) => ({
                value: entry.id,
                label: entry.label,
              }))}
            />
            {draft.mode === QUERY_MODE_CHASE ? (
              <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
                Top 10 composition is an Index Premium capability.
              </p>
            ) : null}
          </ExplorerDisclosure>
        ) : null}
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
            disabled={loading || !spec || noChanges || (!editing && alreadyActive) || (!prepared && !access.allowed)}
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
    <MarketExplorerExactItemPicker
      asset={draft.asset}
      open={exactOpen && draft.membershipMode === QUERY_MEMBERSHIP_EXPLICIT}
      selectedItems={draft.exactItems || []}
      onChange={builder.setExactItems}
      onClose={() => { setExactOpen(false); setTimeout(() => exactTriggerRef.current?.focus(), 0); }}
      onBuild={() => build(false)}
      onSaveAsNew={editing ? () => build(true) : null}
      buildLabel={editing ? "Update Market" : "Build Market"}
      buildStatus={buildStatus}
      buildMessage={message}
      narrowingSummary={narrowingSummary}
      onClearNarrowing={() => builder.replace({ ...draft, eraIds: [], setIds: [], segmentIds: [], pokemonIds: [], priceSegmentIds: [], releaseAgeCohortIds: [] })}
    />
  </>);
}
