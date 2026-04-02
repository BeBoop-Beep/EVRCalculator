"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import CollectionPerformanceCard from "@/components/Collection/CollectionPerformanceCard";
import CollectionScopeFilter from "@/components/Collection/CollectionScopeFilter";
import { getSectionConfig } from "@/config/collectionSectionConfig";
import { buildMyCollectionEntryRoute } from "@/lib/profile/collectionRoutes";
import { filterCollectionByTCG, getAvailableTCGs } from "@/lib/profile/collectionValueHistory";

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function buildMyCollectionItemHref(item) {
  return buildMyCollectionEntryRoute(item);
}

function calculateCollectionStats(items) {
  const totalValue = items.reduce((sum, item) => {
    const val = parseCurrencyValue(item.valueLabel);
    return sum + val;
  }, 0);
  const investedValue = items.reduce((sum, item) => {
    const parsedCostBasis = Number(item?.cost_basis);
    const currentValue = parseCurrencyValue(item.valueLabel);
    const base = Number.isFinite(parsedCostBasis) && parsedCostBasis > 0
      ? parsedCostBasis
      : currentValue * 0.84;
    return sum + base;
  }, 0);

  const sealedItems = items.filter((item) => item.productType || !item.cardNumber);

  return {
    totalItems: items.length,
    totalValue: `$${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    investedValue: `$${investedValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    sealedCount: sealedItems.length,
    config: {
      itemsLabel: "Total Items",
      valueLabel: "Collection Value",
      sealedLabel: "Sealed Products",
    },
  };
}

const MOCK_ITEMS = [
  {
    id: "1",
    collectible_type: "card",
    collectible_id: "card-1",
    name: "Pikachu ex",
    set: "Scarlet & Violet",
    cardNumber: "025/102",
    condition: "Near Mint",
    imageUrl: null,
    valueLabel: "$45.50",
    cost_basis: 32.25,
    isFoil: false,
  },
  {
    id: "2",
    collectible_type: "card",
    collectible_id: "card-2",
    name: "Charizard ex",
    set: "Scarlet & Violet",
    cardNumber: "003/102",
    condition: "Mint",
    imageUrl: null,
    valueLabel: "$120.00",
    cost_basis: 79,
    isFoil: true,
  },
  {
    id: "3",
    collectible_type: "sealed_product",
    collectible_id: "sealed-1",
    name: "Booster Box - Scarlet & Violet",
    set: "Scarlet & Violet",
    productType: "Booster Box",
    condition: "Sealed",
    imageUrl: null,
    valueLabel: "$89.99",
    cost_basis: 150,
  },
  {
    id: "4",
    collectible_type: "card",
    collectible_id: "card-4",
    name: "Blastoise",
    set: "Base Set",
    cardNumber: "002/102",
    condition: "Lightly Played",
    imageUrl: null,
    valueLabel: "$15.00",
    cost_basis: 11,
  },
];

export default function MyCollectionPage() {
  const router = useRouter();
  const config = getSectionConfig("collection");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [viewMode, setViewMode] = useState("continuous");
  const [activeTCGs, setActiveTCGs] = useState(["All"]);
  const [timeRange, setTimeRange] = useState("7D");

  const availableTCGs = useMemo(() => getAvailableTCGs(MOCK_ITEMS), []);

  // Filter by TCG first, then apply other filters
  const tcgFilteredItems = useMemo(() => {
    if (!activeTCGs || activeTCGs.length === 0 || activeTCGs.includes("All")) {
      return MOCK_ITEMS;
    }

    return MOCK_ITEMS.filter((item) => {
      return activeTCGs.some((tcg) => filterCollectionByTCG([item], tcg).length > 0);
    });
  }, [activeTCGs]);

  const filteredAndSortedItems = useMemo(() => {
    let result = [...tcgFilteredItems];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          (item.set && item.set.toLowerCase().includes(query))
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
        result.sort((a, b) => {
          const aVal = parseCurrencyValue(a.valueLabel);
          const bVal = parseCurrencyValue(b.valueLabel);
          return bVal - aVal;
        });
        break;
      case "value-asc":
        result.sort((a, b) => {
          const aVal = parseCurrencyValue(a.valueLabel);
          const bVal = parseCurrencyValue(b.valueLabel);
          return aVal - bVal;
        });
        break;
      case "name-asc":
        result.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "name-desc":
        result.sort((a, b) => b.name.localeCompare(a.name));
        break;
      default:
        break;
    }

    return result;
  }, [searchQuery, activeFilters, sortBy, tcgFilteredItems]);

  const isEmpty = filteredAndSortedItems.length === 0 && !isLoading;
  const filteredStats = useMemo(() => calculateCollectionStats(filteredAndSortedItems), [filteredAndSortedItems]);
  const handleSetAssetSpotlight = (asset) => {
    if (!asset?.id) return;
    router.push(`/account-settings?spotlightAssetId=${encodeURIComponent(String(asset.id))}#spotlight-asset`);
  };

  const activeTCGSelections = useMemo(
    () =>
      activeTCGs
        .filter((tcg) => tcg !== "All")
        .map((tcg) => ({
          id: `tcg-${tcg}`,
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

  const handleAddCard = () => {
    router.push("/cards");
  };

  const handleAddSealedProduct = () => {
    router.push("/products");
  };

  const handleImportCollection = () => {
    router.push("/my-portfolio");
  };

  return (
    <section className="space-y-6">
      {/* Main Collection Section */}
      <CollectionSectionLayout
        config={config}
        items={filteredAndSortedItems}
        isLoading={isLoading}
        isEmpty={isEmpty}
        onSearch={setSearchQuery}
        onFiltersChange={setActiveFilters}
        onSortChange={setSortBy}
        onViewChange={setViewMode}
        showHeader={false}
        viewMode={viewMode}
        variant="detailed"
        showStats={false}
        stats={filteredStats}
        contentAfterHeader={(
          <CollectionPerformanceCard
            initialRange={timeRange}
            tcg={activeTCGs.length === 1 ? activeTCGs[0] : "All"}
            onRangeChange={setTimeRange}
            totalItems={MOCK_ITEMS.length}
            totalValue={filteredStats.totalValue}
            investedValue={filteredStats.investedValue}
          />
        )}
        leadingFilterControls={(
          <CollectionScopeFilter
            options={availableTCGs}
            selectedValues={activeTCGs}
            onTCGChange={setActiveTCGs}
          />
        )}
        extraActiveSelections={activeTCGSelections}
        onClearAllFilters={handleClearAllFilters}
        getItemHref={buildMyCollectionItemHref}
        onSetAssetSpotlight={handleSetAssetSpotlight}
        showAddAction
        onAddCard={handleAddCard}
        onAddSealedProduct={handleAddSealedProduct}
        onImportCollection={handleImportCollection}
        emptyStateTitle="No collection items yet"
        emptyStateDesc="Start by adding cards, sealed products, or other items to your collection."
      />
    </section>
  );
}
