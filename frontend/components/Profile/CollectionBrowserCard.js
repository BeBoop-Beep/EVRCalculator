"use client";

import SectionSearchBar from "@/components/Profile/SectionSearchBar";
import SectionFilterBar from "@/components/Profile/SectionFilterBar";
import SectionSortControl from "@/components/Profile/SectionSortControl";
import SectionViewToggle from "@/components/Profile/SectionViewToggle";
import CollectionAddActionMenu from "@/components/Profile/CollectionAddActionMenu";
import SectionEmptyState from "@/components/Profile/SectionEmptyState";
import SharedCollectionGrid from "@/components/Profile/SharedCollectionGrid";

export default function CollectionBrowserCard({
  config,
  items = [],
  isLoading = false,
  isEmpty = false,
  view = "continuous",
  activeFilterCount = 0,
  onSearch = () => {},
  onFilterChange = () => {},
  onSortChange = () => {},
  onViewChange = () => {},
  activeFilters = {},
  leadingFilterControls = null,
  extraActiveSelections = [],
  onClearAllFilters = null,
  variant = "detailed",
  getItemHref = null,
  onSetAssetSpotlight = null,
  showAddAction = false,
  onAddCard = () => {},
  onAddSealedProduct = () => {},
  onImportCollection = () => {},
  emptyStateTitle = "No items yet",
  emptyStateDesc = "Start building your collection.",
}) {
  return (
    <section className="dashboard-panel rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
      <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
              Collection Browser
            </p>
          </div>
        </div>

        {(config.supportsSearch || config.supportsSorting || config.supportsViewToggle || showAddAction) && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {config.supportsSearch && (
              <div className="flex-1">
                <SectionSearchBar
                  placeholder={`Search ${config.title.toLowerCase()}...`}
                  onSearch={onSearch}
                  isLoading={isLoading}
                />
              </div>
            )}

            <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
              {config.supportsSorting && (
                <SectionSortControl
                  sortOptions={config.sortOptions}
                  defaultSort={config.defaultSort}
                  onSortChange={onSortChange}
                  isLoading={isLoading}
                />
              )}

              {config.supportsViewToggle && (
                <SectionViewToggle
                  currentView={view}
                  onViewChange={onViewChange}
                  isLoading={isLoading}
                />
              )}

              {showAddAction ? (
                <CollectionAddActionMenu
                  onAddCard={onAddCard}
                  onAddSealedProduct={onAddSealedProduct}
                  onImportCollection={onImportCollection}
                  isLoading={isLoading}
                />
              ) : null}
            </div>
          </div>
        )}

        {config.supportsFilters && config.filters.length > 0 && (
          <div className="mt-4">
            <SectionFilterBar
              filters={config.filters}
              activeFilters={activeFilters}
              onFilterChange={onFilterChange}
              isLoading={isLoading}
              leadingControls={leadingFilterControls}
              extraActiveSelections={extraActiveSelections}
              onClearAll={onClearAllFilters}
            />
          </div>
        )}

        <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {isLoading ? "Loading..." : `${items.length} item${items.length !== 1 ? "s" : ""}`}
              </p>
              {activeFilterCount > 0 ? (
                <span className="rounded-full bg-[var(--accent)]/10 px-2 py-1 text-xs font-medium text-[var(--accent)]">
                  {activeFilterCount} active filter{activeFilterCount !== 1 ? "s" : ""}
                </span>
              ) : null}
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              {view === "binder" ? "Binder mode" : "Continuous scroll"}
            </p>
          </div>

          <div className="mt-4">
            {isEmpty && !isLoading ? (
              <SectionEmptyState title={emptyStateTitle} description={emptyStateDesc} />
            ) : (
              <SharedCollectionGrid
                items={items}
                viewMode={view}
                variant={variant}
                isLoading={isLoading}
                emptyMessage={emptyStateDesc}
                getItemHref={getItemHref}
                onSetAssetSpotlight={onSetAssetSpotlight}
              />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}