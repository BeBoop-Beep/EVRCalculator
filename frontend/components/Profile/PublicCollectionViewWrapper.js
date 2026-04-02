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
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(publicCollectionConfig.defaultSort);
  const [viewMode, setViewMode] = useState("continuous");
  const [activeTCGs, setActiveTCGs] = useState(["All"]);
  const [selectedRange, setSelectedRange] = useState("7D");
  const availableTCGs = useMemo(() => getAvailableTCGs(items), [items]);

  const tcgFilteredItems = useMemo(() => {
    if (!activeTCGs || activeTCGs.length === 0 || activeTCGs.includes("All")) {
      return items;
    }

    return items.filter((item) => {
      return activeTCGs.some((tcg) => filterCollectionByTCG([item], tcg).length > 0);
    });
  }, [items, activeTCGs]);

  const filteredAndSortedItems = useMemo(() => {
    let result = [...tcgFilteredItems];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name?.toLowerCase().includes(query)
          || item.set?.toLowerCase().includes(query)
      );
    }

    if (activeFilters.type && activeFilters.type.length > 0) {
      result = result.filter((item) => {
        if (activeFilters.type.includes("cards")) return item.cardNumber;
        if (activeFilters.type.includes("sealed")) return item.productType;
        return false;
      });
    }

    switch (sortBy) {
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
  }, [tcgFilteredItems, searchQuery, activeFilters, sortBy]);

  const activeTCGSelections = useMemo(
    () =>
      activeTCGs
        .filter((tcg) => tcg !== "All")
        .map((tcg) => ({
          id: `public-tcg-${tcg}`,
          label: `TCG: ${tcg}`,
          onRemove: () => {
            setActiveTCGs((prev) => {
              const next = prev.filter((value) => value !== tcg && value !== "All");
              return next.length > 0 ? next : ["All"];
            });
          },
        })),
    [activeTCGs]
  );

  const handleClearAllFilters = () => {
    setActiveTCGs(["All"]);
  };

  const isEmpty = filteredAndSortedItems.length === 0;

  const buildPublicCollectionItemHref = (item) => {
    return buildPublicCollectibleRouteFromEntry(item);
  };

  return (
    <>
      {/* Collection Performance Card */}
      <CollectionPerformanceCard
        initialRange={selectedRange}
        tcg={activeTCGs.length === 1 ? activeTCGs[0] : "All"}
        onRangeChange={setSelectedRange}
        totalItems={stats.totalItems || items.length}
        totalValue={stats.totalValue || "$0"}
      />

      {/* Main Collection Grid Section */}
      <CollectionSectionLayout
        config={publicCollectionConfig}
        items={filteredAndSortedItems}
        isLoading={false}
        isEmpty={isEmpty}
        onSearch={setSearchQuery}
        onFiltersChange={setActiveFilters}
        onViewChange={setViewMode}
        viewMode={viewMode}
        variant="detailed"
        showStats={false}
        stats={stats}
        showHeader={false}
        leadingFilterControls={(
          <CollectionScopeFilter
            options={availableTCGs}
            selectedValues={activeTCGs}
            onTCGChange={setActiveTCGs}
          />
        )}
        extraActiveSelections={activeTCGSelections}
        onClearAllFilters={handleClearAllFilters}
        getItemHref={buildPublicCollectionItemHref}
        emptyStateTitle="No shared collection items"
        emptyStateDesc="This collector hasn't shared any collection items yet."
      />
    </>
  );
}
