"use client";

import { useMemo, useState } from "react";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import CollectionPerformanceCard from "@/components/Collection/CollectionPerformanceCard";
import CollectionScopeFilter from "@/components/Collection/CollectionScopeFilter";
import { buildPublicCollectibleRouteFromEntry } from "@/lib/profile/collectionRoutes";
import { filterCollectionByTCG, getAvailableTCGs } from "@/lib/profile/collectionValueHistory";

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

const publicCollectionConfig = {
  id: "public-collection",
  title: "Collection",
  eyebrow: "Public Collection",
  subtitle: "",
  supportsSearch: true,
  supportsFilters: true,
  supportsSorting: true,
  supportsViewToggle: true,
  filters: [
    {
      id: "type",
      label: "Type",
      type: "select",
      options: [
        { id: "cards", label: "Cards" },
        { id: "sealed", label: "Sealed" },
        { id: "merchandise", label: "Merchandise" },
      ],
    },
    {
      id: "condition",
      label: "Condition",
      type: "select",
      options: [
        { id: "mint", label: "Mint" },
        { id: "near-mint", label: "Near Mint" },
        { id: "lightly-played", label: "Lightly Played" },
        { id: "moderately-played", label: "Moderately Played" },
        { id: "heavily-played", label: "Heavily Played" },
      ],
    },
  ],
  sortOptions: [
    { id: "recent", label: "Recently Added" },
    { id: "value-desc", label: "Value (High to Low)" },
    { id: "value-asc", label: "Value (Low to High)" },
    { id: "name-asc", label: "Name (A-Z)" },
    { id: "name-desc", label: "Name (Z-A)" },
  ],
  defaultSort: "recent",
};

/**
 * Client-side wrapper for public collection view
 * Handles view mode toggle, performance analytics, and layout
 */
export default function PublicCollectionViewWrapper({
  items = [],
  stats = {},
  username = "",
  showPerformanceCard = true,
  localNavToolState = null,
  localNavControlsActive = false,
}) {
  const [searchQuery, setSearchQuery] = useState(localNavToolState?.q || "");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(localNavToolState?.sort || publicCollectionConfig.defaultSort);
  const [viewMode, setViewMode] = useState(localNavToolState?.view || "continuous");
  const [activeTCGs, setActiveTCGs] = useState(["All"]);
  const [selectedRange, setSelectedRange] = useState("7D");
  const availableTCGs = useMemo(() => getAvailableTCGs(items), [items]);

  const resolvedSearchQuery = localNavControlsActive ? String(localNavToolState?.q || "") : searchQuery;
  const resolvedSortBy = localNavControlsActive
    ? String(localNavToolState?.sort || publicCollectionConfig.defaultSort)
    : sortBy;
  const resolvedViewMode = localNavControlsActive ? String(localNavToolState?.view || "continuous") : viewMode;

  const resolvedActiveFilters = useMemo(() => {
    if (!localNavControlsActive) return activeFilters;

    const filters = {};
    if (localNavToolState?.type) {
      filters.type = [localNavToolState.type];
    }
    if (localNavToolState?.condition) {
      filters.condition = [localNavToolState.condition];
    }
    return filters;
  }, [activeFilters, localNavControlsActive, localNavToolState]);

  const resolvedActiveTCGs = useMemo(() => {
    if (!localNavControlsActive) return activeTCGs;
    return localNavToolState?.tcg ? [localNavToolState.tcg] : ["All"];
  }, [activeTCGs, localNavControlsActive, localNavToolState]);

  const handleSearchChange = (query) => {
    if (localNavControlsActive) return;
    setSearchQuery(query);
  };

  const handleFiltersChange = (filters) => {
    if (localNavControlsActive) return;
    setActiveFilters(filters);
  };

  const handleSortChange = (sortId) => {
    if (localNavControlsActive) return;
    setSortBy(sortId);
  };

  const handleViewChange = (nextView) => {
    if (localNavControlsActive) return;
    setViewMode(nextView);
  };

  const normalizeCondition = (value) => {
    const normalized = String(value || "").trim().toLowerCase();
    const map = {
      "mint": ["mint"],
      "near-mint": ["near mint", "nm"],
      "lightly-played": ["lightly played", "lp"],
      "moderately-played": ["moderately played", "mp"],
      "heavily-played": ["heavily played", "hp"],
      "sealed": ["sealed"],
    };
    return map[normalized] || [];
  };

  const tcgFilteredItems = useMemo(() => {
    if (!resolvedActiveTCGs || resolvedActiveTCGs.length === 0 || resolvedActiveTCGs.includes("All")) {
      return items;
    }

    return items.filter((item) => {
      return resolvedActiveTCGs.some((tcg) => filterCollectionByTCG([item], tcg).length > 0);
    });
  }, [items, resolvedActiveTCGs]);

  const filteredAndSortedItems = useMemo(() => {
    let result = [...tcgFilteredItems];

    if (resolvedSearchQuery.trim()) {
      const query = resolvedSearchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name?.toLowerCase().includes(query)
          || item.set?.toLowerCase().includes(query)
      );
    }

    if (resolvedActiveFilters.type && resolvedActiveFilters.type.length > 0) {
      result = result.filter((item) => {
        const matchesCards = resolvedActiveFilters.type.includes("cards") && Boolean(item.cardNumber);
        const matchesSealed = resolvedActiveFilters.type.includes("sealed") && Boolean(item.productType);
        const matchesMerch = resolvedActiveFilters.type.includes("merchandise") && item.collectible_type === "merchandise";
        return matchesCards || matchesSealed || matchesMerch;
      });
    }

    if (resolvedActiveFilters.condition && resolvedActiveFilters.condition.length > 0) {
      const acceptedConditions = normalizeCondition(resolvedActiveFilters.condition[0]);
      if (acceptedConditions.length > 0) {
        result = result.filter((item) => acceptedConditions.includes(String(item.condition || "").toLowerCase()));
      }
    }

    switch (resolvedSortBy) {
      case "value-desc":
        result.sort((a, b) => parseCurrencyValue(b.valueLabel) - parseCurrencyValue(a.valueLabel));
        break;
      case "value-asc":
        result.sort((a, b) => parseCurrencyValue(a.valueLabel) - parseCurrencyValue(b.valueLabel));
        break;
      case "name-asc":
        result.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
        break;
      case "name-desc":
        result.sort((a, b) => String(b.name || "").localeCompare(String(a.name || "")));
        break;
      default:
        break;
    }

    return result;
  }, [tcgFilteredItems, resolvedSearchQuery, resolvedActiveFilters, resolvedSortBy]);

  const activeTCGSelections = useMemo(
    () =>
      resolvedActiveTCGs
        .filter((tcg) => tcg !== "All")
        .map((tcg) => ({
          id: `public-tcg-${tcg}`,
          label: `TCG: ${tcg}`,
          onRemove: () => {
            if (localNavControlsActive) return;
            setActiveTCGs((prev) => {
              const next = prev.filter((value) => value !== tcg && value !== "All");
              return next.length > 0 ? next : ["All"];
            });
          },
        })),
    [resolvedActiveTCGs, localNavControlsActive]
  );

  const handleClearAllFilters = () => {
    if (localNavControlsActive) return;
    setActiveTCGs(["All"]);
  };

  const isEmpty = filteredAndSortedItems.length === 0;

  const buildPublicCollectionItemHref = (item) => {
    return buildPublicCollectibleRouteFromEntry(item);
  };

  return (
    <>
      {/* Collection Performance Card */}
      {showPerformanceCard && (
        <CollectionPerformanceCard
          initialRange={selectedRange}
          tcg={resolvedActiveTCGs.length === 1 ? resolvedActiveTCGs[0] : "All"}
          onRangeChange={setSelectedRange}
          totalItems={stats.totalItems || items.length}
          totalValue={stats.totalValue || "$0"}
          investedValue={stats.investedValue || null}
          showSummaryMetrics={false}
        />
      )}

      {/* Main Collection Grid Section */}
      <CollectionSectionLayout
        config={publicCollectionConfig}
        items={filteredAndSortedItems}
        isLoading={false}
        isEmpty={isEmpty}
        onSearch={handleSearchChange}
        onFiltersChange={handleFiltersChange}
        onSortChange={handleSortChange}
        onViewChange={handleViewChange}
        viewMode={resolvedViewMode}
        variant="detailed"
        showStats={false}
        stats={stats}
        showHeader={false}
        leadingFilterControls={localNavControlsActive ? null : (
          <CollectionScopeFilter
            options={availableTCGs}
            selectedValues={resolvedActiveTCGs}
            onTCGChange={setActiveTCGs}
          />
        )}
        activeFilters={resolvedActiveFilters}
        selectedType={resolvedActiveFilters.type?.[0] || "all"}
        extraActiveSelections={activeTCGSelections}
        onClearAllFilters={handleClearAllFilters}
        getItemHref={buildPublicCollectionItemHref}
        emptyStateTitle="No shared collection items"
        emptyStateDesc="This collector hasn't shared any collection items yet."
        hideBrowserControls={localNavControlsActive}
        searchPlaceholder="Search this collection"
        showAdvancedFilters={!localNavControlsActive}
      />
    </>
  );
}
