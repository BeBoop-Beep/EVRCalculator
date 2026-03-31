"use client";

import { useState, useMemo } from "react";
import RoutePageShell from "@/components/Profile/RoutePageShell";
import SectionSearchBar from "@/components/Profile/SectionSearchBar";
import SectionFilterBar from "@/components/Profile/SectionFilterBar";
import SectionSortControl from "@/components/Profile/SectionSortControl";
import SectionViewToggle from "@/components/Profile/SectionViewToggle";
import SectionLoadingState from "@/components/Profile/SectionLoadingState";
import SectionEmptyState from "@/components/Profile/SectionEmptyState";

/**
 * Reusable layout framework for My Collection sections
 * Handles header, controls, and results layout with section-specific configuration
 *
 * @param {object} config - Section configuration object from collectionSectionConfig
 * @param {array} items - Array of items to display (filtered/sorted)
 * @param {bool} isLoading - Whether data is loading
 * @param {bool} isEmpty - Whether there are no results
 * @param {function} renderItem - Function to render each item in the grid/list
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
  renderItem = null,
  onSearch = () => {},
  onFiltersChange = () => {},
  onSortChange = () => {},
  onViewChange = () => {},
  emptyStateTitle = "No items yet",
  emptyStateDesc = "Start building your collection.",
  viewMode = "grid",
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [view, setView] = useState(config.supportsViewToggle ? viewMode : "grid");

  // Handle search
  const handleSearch = (query) => {
    setSearchQuery(query);
    onSearch(query);
  };

  // Handle filter changes
  const handleFilterChange = (filterId, values) => {
    const newFilters = { ...activeFilters };
    if (values && values.length > 0) {
      newFilters[filterId] = values;
    } else {
      delete newFilters[filterId];
    }
    setActiveFilters(newFilters);
    onFiltersChange(newFilters);
  };

  // Handle sort changes
  const handleSortChange = (sortId) => {
    setSortBy(sortId);
    onSortChange(sortId);
  };

  // Handle view toggle
  const handleViewChange = (viewType) => {
    if (config.supportsViewToggle) {
      setView(viewType);
      onViewChange(viewType);
    }
  };

  // Count active filters
  const activeFilterCount = useMemo(() => {
    return Object.values(activeFilters).reduce((sum, val) => sum + (val ? val.length : 0), 0);
  }, [activeFilters]);

  return (
    <section className="space-y-6">
      {/* Header */}
      <RoutePageShell
        eyebrow={config.eyebrow}
        title={config.title}
        subtitle={config.subtitle}
      />

      {/* Controls Bar */}
      <div className="space-y-4">
        {/* Search & Sort Row */}
        {(config.supportsSearch || config.supportsSorting || config.supportsViewToggle) && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {config.supportsSearch && (
              <div className="flex-1 sm:max-w-sm">
                <SectionSearchBar
                  placeholder={`Search ${config.title.toLowerCase()}...`}
                  onSearch={handleSearch}
                  isLoading={isLoading}
                />
              </div>
            )}

            <div className="flex flex-wrap gap-2 sm:justify-end">
              {config.supportsSorting && (
                <SectionSortControl
                  sortOptions={config.sortOptions}
                  defaultSort={config.defaultSort}
                  onSortChange={handleSortChange}
                  isLoading={isLoading}
                />
              )}

              {config.supportsViewToggle && (
                <SectionViewToggle
                  currentView={view}
                  onViewChange={handleViewChange}
                  isLoading={isLoading}
                />
              )}
            </div>
          </div>
        )}

        {/* Filters */}
        {config.supportsFilters && config.filters.length > 0 && (
          <div className="dashboard-panel rounded-lg p-4 border border-[var(--border-subtle)]">
            <SectionFilterBar
              filters={config.filters}
              activeFilters={activeFilters}
              onFilterChange={handleFilterChange}
              isLoading={isLoading}
            />
          </div>
        )}
      </div>

      {/* Results Area */}
      <div className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-6">
        {/* Results metadata */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {isLoading ? "Loading..." : `${items.length} items`}
            </p>
            {activeFilterCount > 0 && (
              <span className="rounded-full bg-[var(--accent)]/10 px-2 py-1 text-xs font-medium text-[var(--accent)]">
                {activeFilterCount} filter{activeFilterCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>

        {/* Loading state */}
        {isLoading && <SectionLoadingState variant={view} />}

        {/* Empty state */}
        {!isLoading && isEmpty && (
          <SectionEmptyState
            title={emptyStateTitle}
            description={emptyStateDesc}
            icon={getEmptyStateIcon(config.id)}
          />
        )}

        {/* Results grid/list */}
        {!isLoading && !isEmpty && renderItem && (
          <div
            className={
              view === "list"
                ? "space-y-3"
                : "grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            }
          >
            {items.map((item, idx) => (
              <div key={item.id || idx} className="h-full">{renderItem(item)}</div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/**
 * Get appropriate empty state icon for each section
 */
function getEmptyStateIcon(sectionId) {
  const icons = {
    collection: "🎁",
    binder: "📖",
    shelf: "🏠",
    wishlist: "⭐",
  };
  return icons[sectionId] || "📦";
}
