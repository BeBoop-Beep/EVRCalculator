"use client";

import { useEffect, useMemo, useState } from "react";
import RoutePageShell from "@/components/Profile/RoutePageShell";
import CollectionBrowserCard from "@/components/Profile/CollectionBrowserCard";
import CollectionStatBar from "@/components/Profile/CollectionStatBar";

/**
 * Reusable layout framework for My Collection sections
 * Handles header, controls, and results layout with section-specific configuration
 *
 * @param {object} config - Section configuration object from collectionSectionConfig
 * @param {array} items - Array of items to display (filtered/sorted)
 * @param {bool} isLoading - Whether data is loading
 * @param {bool} isEmpty - Whether there are no results
 * @param {function} onSearch - Callback when search changes
 * @param {function} onFiltersChange - Callback when filters change
 * @param {function} onSortChange - Callback when sort changes
 * @param {function} onViewChange - Callback when view toggles
 * @param {string} emptyStateTitle - Custom empty state title
 * @param {string} emptyStateDesc - Custom empty state description
 */
export default function CollectionSectionLayout({
  config,
  items = [],
  isLoading = false,
  isEmpty = false,
  onSearch = () => {},
  onFiltersChange = () => {},
  onSortChange = () => {},
  onViewChange = () => {},
  emptyStateTitle = "No items yet",
  emptyStateDesc = "Start building your collection.",
  viewMode = "continuous",
  variant = "detailed",
  showStats = true,
  stats = {},
  showHeader = true,
  contentAfterHeader = null,
  leadingFilterControls = null,
  extraActiveSelections = [],
  onClearAllFilters = null,
  getItemHref = null,
  onSetAssetSpotlight = null,
  showAddAction = false,
  onAddCard = () => {},
  onAddSealedProduct = () => {},
  onImportCollection = () => {},
  leftSidebar = null,
  selectedType = null,
  activeFilters = null,
  onTypeFilterChange = null,
  showAdvancedFilters = true,
  hideBrowserControls = false,
  searchPlaceholder = null,
}) {
  const [internalActiveFilters, setInternalActiveFilters] = useState({});
  const [internalSelectedType, setInternalSelectedType] = useState("all");
  const initialView = viewMode || config.defaultView || "continuous";
  const [view, setView] = useState(config.supportsViewToggle ? initialView : "continuous");
  const resolvedActiveFilters = activeFilters ?? internalActiveFilters;
  const resolvedSelectedType = selectedType ?? internalSelectedType;

  // Handle search
  const handleSearch = (query) => {
    onSearch(query);
  };

  // Handle filter changes
  const handleFilterChange = (filterId, values) => {
    const sourceFilters = activeFilters !== null ? resolvedActiveFilters : internalActiveFilters;
    const newFilters = { ...sourceFilters };
    if (values && values.length > 0) {
      newFilters[filterId] = values;
    } else {
      delete newFilters[filterId];
    }

    if (activeFilters === null) {
      setInternalActiveFilters(newFilters);
    }

    onFiltersChange(newFilters);
  };

  // Handle sort changes
  const handleSortChange = (sortId) => {
    onSortChange(sortId);
  };

  // Handle view toggle
  const handleViewChange = (viewType) => {
    if (config.supportsViewToggle) {
      setView(viewType);
      onViewChange(viewType);
    }
  };

  // Handle type filter change
  const handleTypeFilterChange = (typeId) => {
    if (selectedType === null) {
      setInternalSelectedType(typeId);
    }
    onTypeFilterChange?.(typeId);
  };

  // Handle clear all filters (including type)
  const handleClearAllFilters = () => {
    if (activeFilters === null) {
      setInternalActiveFilters({});
    }
    if (selectedType === null) {
      setInternalSelectedType("all");
    }
    onFiltersChange({});
    onTypeFilterChange?.("all");
    onClearAllFilters?.();
  };

  const activeFilterCount = useMemo(
    () =>
      Object.values(resolvedActiveFilters || {}).reduce((sum, value) => sum + (value?.length || 0), 0)
      + (extraActiveSelections?.length || 0),
    [resolvedActiveFilters, extraActiveSelections]
  );

  useEffect(() => {
    if (!showAddAction) return undefined;

    const isTypingTarget = (element) => {
      if (!element || !(element instanceof HTMLElement)) return false;

      const tagName = element.tagName?.toLowerCase();
      if (tagName === "input" || tagName === "textarea") {
        return true;
      }

      return element.isContentEditable || Boolean(element.closest("[contenteditable='true']"));
    };

    const handleKeyDown = (event) => {
      if (event.defaultPrevented || event.repeat) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (String(event.key).toLowerCase() !== "a") return;
      if (isTypingTarget(document.activeElement)) return;

      event.preventDefault();
      onAddCard();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showAddAction, onAddCard]);

  return (
    <section className="space-y-6">
      {showHeader ? (
        <RoutePageShell
          eyebrow={config.eyebrow}
          title={config.title}
          subtitle={config.subtitle}
        />
      ) : null}

      {contentAfterHeader}

      {/* Collection Stats Bar */}
      {showStats ? (
        <CollectionStatBar
          totalItems={stats.totalItems ?? items.length}
          totalValue={stats.totalValue ?? "$0"}
          sealedCount={stats.sealedCount ?? 0}
          statsConfig={stats.config}
        />
      ) : null}

      <div className={leftSidebar ? "grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]" : ""}>
        {leftSidebar ? <div className="min-w-0">{leftSidebar}</div> : null}
        <div className="min-w-0">
          <CollectionBrowserCard
            config={config}
            items={items}
            isLoading={isLoading}
            isEmpty={isEmpty}
            view={view}
            activeFilterCount={activeFilterCount}
            onSearch={handleSearch}
            onFilterChange={handleFilterChange}
            onTypeFilterChange={handleTypeFilterChange}
            onSortChange={handleSortChange}
            onViewChange={handleViewChange}
            activeFilters={resolvedActiveFilters}
            selectedType={resolvedSelectedType}
            leadingFilterControls={leadingFilterControls}
            extraActiveSelections={extraActiveSelections}
            onClearAllFilters={handleClearAllFilters}
            variant={variant}
            getItemHref={getItemHref}
            onSetAssetSpotlight={onSetAssetSpotlight}
            showAddAction={showAddAction}
            onAddCard={onAddCard}
            onAddSealedProduct={onAddSealedProduct}
            onImportCollection={onImportCollection}
            emptyStateTitle={emptyStateTitle}
            emptyStateDesc={emptyStateDesc}
            showAdvancedFilters={showAdvancedFilters}
            hideControls={hideBrowserControls}
            searchPlaceholder={searchPlaceholder}
          />
        </div>
      </div>
    </section>
  );
}
