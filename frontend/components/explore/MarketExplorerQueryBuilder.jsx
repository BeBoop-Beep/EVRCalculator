"use client";
import { useMemo, useState } from "react";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import DarkSelect from "@/components/ui/DarkSelect";
import ExplorerDisclosure from "./ExplorerDisclosure";
import ExplorerMarketOption from "./ExplorerMarketOption";
import ExplorerPlanLockPanel from "./ExplorerPlanLockPanel";
import useMarketExplorerBuilderDraft from "@/hooks/explore/useMarketExplorerBuilderDraft";
import {
  QUERY_ASSET_CARDS,
  QUERY_ASSET_SEALED,
  QUERY_MODE_ALL,
  QUERY_MODE_CHASE,
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
  options = null,
  optionsStatus = "loading",
  optionsMessage = "",
  currentPlan = null,
  isAuthenticated = false,
  preparedSeries = [],
  activeSeries = [],
  benchmarkEntries = [],
  selectedSeriesCount = 0,
  onAddQuery,
  onAddPrepared,
  onToggleBenchmark,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedScreenId, setSelectedScreenId] = useState(null);
  const loadedOptions = useMarketExplorerFilterOptions();
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
        ? resolveScreenResults(selectedScreen, preparedSeries)
        : [],
    [selectedScreen, preparedSeries],
  );
  const chooseAll = (asset) => {
    builder.replace({
      asset,
      eraIds: [],
      setIds: [],
      segmentIds: [],
      pokemonIds: [],
      priceSegmentIds: [],
      releaseAgeCohortIds: [],
      mode: QUERY_MODE_ALL,
      topN: null,
    });
    setMessage("");
  };
  const build = async () => {
    if (alreadyActive) return;
    if (!prepared && !access.allowed) {
      setMessage(
        `This market requires Index ${access.requiredPlan === "premium" ? "Premium" : "Plus"}.`,
      );
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const outcome = prepared
        ? onAddPrepared?.(prepared.key)
        : await onAddQuery?.(spec);
      setMessage(
        outcome === "duplicate" ? "Already active." : "Added to comparison.",
      );
    } catch (error) {
      setMessage(
        error?.message ||
          "The market query service is temporarily unavailable.",
      );
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
    if (draft.asset !== asset)
      return (
        <button
          type="button"
          onClick={() => builder.setAsset(asset)}
          className="mt-2 min-h-11 w-full rounded-md border border-[var(--border-subtle)] px-3 text-left text-xs text-[var(--text-primary)] desk:min-h-0"
        >
          Edit this asset
        </button>
      );
    const presentation = presentationFor(asset);
    return (
      <div className="mt-2 space-y-2">
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
      </div>
    );
  };
  const body = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        data-market-builder-scroll-region
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-3 sm:px-4"
      >
        <ExplorerDisclosure id="rawCardsBuilder" title="Raw Cards" defaultOpen>
          <button
            type="button"
            data-builder-all-raw-cards
            onClick={() => chooseAll(QUERY_ASSET_CARDS)}
            className="min-h-11 w-full rounded-md border border-[var(--border-subtle)] px-3 text-left text-xs font-semibold text-[var(--text-primary)] desk:min-h-0"
          >
            All Raw Cards
          </button>
          {assetControls(QUERY_ASSET_CARDS)}
        </ExplorerDisclosure>
        <ExplorerDisclosure id="sealedBuilder" title="Sealed">
          <button
            type="button"
            data-builder-all-sealed
            onClick={() => chooseAll(QUERY_ASSET_SEALED)}
            className="min-h-11 w-full rounded-md border border-[var(--border-subtle)] px-3 text-left text-xs font-semibold text-[var(--text-primary)] desk:min-h-0"
          >
            All Sealed
          </button>
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
        <ExplorerDisclosure id="screens" title="Screens">
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
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    builder.replace(
                      draftForScreenResult(selectedScreen, null, draft),
                    )
                  }
                  className="w-full rounded-md border border-[var(--border-subtle)] px-2 py-2 text-left text-[11px] text-[var(--text-primary)]"
                >
                  Use in Market Builder
                </button>
              )}
            </div>
          ) : null}
        </ExplorerDisclosure>
        <ExplorerDisclosure id="benchmarks" title="Benchmarks">
          {paid ? (
            <PreparedOptionList
              entries={benchmarkEntries}
              onToggle={onToggleBenchmark}
              selectedSeriesCount={selectedSeriesCount}
            />
          ) : (
            accessPanel("Add prepared comparison benchmarks with Index Plus.")
          )}
        </ExplorerDisclosure>
        {paid ? (
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
        className="sticky bottom-0 border-t border-[var(--border-subtle)] bg-[var(--surface-page)]/95 px-3 py-3 backdrop-blur sm:px-4"
      >
        <p className="text-[9px] font-semibold uppercase tracking-[0.09em] text-[var(--text-secondary)]">
          Current Market
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          {draft.asset === QUERY_ASSET_SEALED ? "Sealed" : "Raw Cards"}
        </p>
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
            onClick={() => {
              builder.clear();
              setMessage("");
            }}
            className="min-h-11 rounded-md border border-[var(--border-subtle)] px-3 text-xs font-semibold text-[var(--text-secondary)] desk:min-h-0"
          >
            Clear
          </button>
          <button
            type="button"
            data-market-builder-build
            onClick={build}
            disabled={
              loading || alreadyActive || (!prepared && !access.allowed)
            }
            className="min-h-11 rounded-md border border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.16)] px-3 text-xs font-semibold text-[rgb(45,212,191)] disabled:opacity-50 desk:min-h-0"
          >
            {alreadyActive
              ? "Already Active"
              : loading
                ? "Building…"
                : !prepared && !access.allowed
                  ? "Build Market 🔒"
                  : "Build Market"}
          </button>
        </div>
        {message ? (
          <p
            role="status"
            className="mt-2 text-[11px] text-[var(--text-secondary)]"
          >
            {message}
          </p>
        ) : null}
      </div>
    </div>
  );
  return (
    <section
      data-market-explorer-filters
      data-market-builder-asset={draft.asset}
      className="flex min-w-0 flex-col desk:max-h-[42rem]"
      aria-labelledby="market-builder-heading"
    >
      <div className="flex items-center gap-2 px-3 py-3 sm:px-4">
        <div>
          <h2
            id="market-builder-heading"
            className="text-[16px] font-semibold text-[var(--text-primary)]"
          >
            Market Builder
          </h2>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            Define a market, preview it, then build.
          </p>
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
  );
}
