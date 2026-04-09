"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import CollectionAnalyticsSurface from "@/components/Collection/CollectionAnalyticsSurface";
import GlobalFilterPanel from "@/components/Profile/GlobalFilterPanel";
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

function getAssetTypeForItem(item) {
  if (item?.collectible_type === "card" || item?.cardNumber) return "cards";
  if (item?.collectible_type === "sealed_product" || item?.productType) return "sealed";
  if (item?.collectible_type === "merchandise") return "merchandise";
  return "cards";
}

function deriveEraFromItem(item) {
  const source = `${item?.release || ""} ${item?.set || ""}`.toLowerCase();

  if (!source.trim()) return "Unknown Era";
  if (source.includes("scarlet") || source.includes("violet") || /\bsv\b/.test(source)) {
    return "Scarlet & Violet Era";
  }
  if (source.includes("sword") || source.includes("shield") || /\bswsh\b/.test(source)) {
    return "Sword & Shield Era";
  }
  if (source.includes("sun") || source.includes("moon")) {
    return "Sun & Moon Era";
  }
  if (source.includes("base set") || source.includes("jungle") || source.includes("fossil") || source.includes("neo")) {
    return "Vintage Era";
  }

  return "Other Era";
}

function getBinderLabel(item) {
  return item?.binder || item?.binderName || item?.binder_id || item?.binderId || null;
}

function getResolvedBinderLabel(item) {
  return getBinderLabel(item) || "Unassigned";
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

const INITIAL_GLOBAL_FILTERS = {
  tcg: ["All"],
  set: [],
  assetType: "all",
  condition: [],
  era: [],
  binder: [],
};

export default function MyCollectionPageClient({ initialItems = [] }) {
  const router = useRouter();
  const config = getSectionConfig("collection");
  const [isLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [globalFilters, setGlobalFilters] = useState(INITIAL_GLOBAL_FILTERS);
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [viewMode, setViewMode] = useState("continuous");
  const [collectionItems] = useState(Array.isArray(initialItems) ? initialItems : []);

  const availableTCGs = useMemo(() => getAvailableTCGs(collectionItems), [collectionItems]);
  const filterOptions = useMemo(() => {
    const typeFilter = config.filters?.find((filter) => filter.id === "type");
    const binderOptions = Array.from(new Set(collectionItems.map((item) => getResolvedBinderLabel(item)))).sort((a, b) => a.localeCompare(b));

    return {
      tcg: availableTCGs,
      set: Array.from(new Set(collectionItems.map((item) => item.set).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
      assetType: [
        { value: "all", label: "All" },
        ...(typeFilter?.options || []).map((option) => ({
          value: option.id,
          label: option.label,
        })),
      ],
      condition: Array.from(new Set(collectionItems.map((item) => item.condition).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
      era: Array.from(new Set(collectionItems.map((item) => deriveEraFromItem(item)).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
      binder: binderOptions,
    };
  }, [availableTCGs, collectionItems, config.filters]);

  const handleGlobalFilterChange = (key, value) => {
    setGlobalFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleTypeChipChange = (typeId) => {
    setGlobalFilters((prev) => ({
      ...prev,
      assetType: typeId || "all",
    }));
  };

  const handleClearAllFilters = () => {
    setGlobalFilters(INITIAL_GLOBAL_FILTERS);
  };

  const analyticsFilteredItems = useMemo(() => {
    let result = [...collectionItems];

    if (globalFilters.tcg && globalFilters.tcg.length > 0 && !globalFilters.tcg.includes("All")) {
      result = result.filter((item) =>
        globalFilters.tcg.some((tcg) => filterCollectionByTCG([item], tcg).length > 0)
      );
    }

    if (globalFilters.set && globalFilters.set.length > 0) {
      result = result.filter((item) => globalFilters.set.includes(item.set));
    }

    if (globalFilters.assetType && globalFilters.assetType !== "all") {
      result = result.filter((item) => getAssetTypeForItem(item) === globalFilters.assetType);
    }

    if (globalFilters.condition && globalFilters.condition.length > 0) {
      result = result.filter((item) => item.condition && globalFilters.condition.includes(item.condition));
    }

    if (globalFilters.era && globalFilters.era.length > 0) {
      result = result.filter((item) => globalFilters.era.includes(deriveEraFromItem(item)));
    }

    if (globalFilters.binder && globalFilters.binder.length > 0) {
      result = result.filter((item) => {
        const binderLabel = getResolvedBinderLabel(item);
        return globalFilters.binder.includes(binderLabel);
      });
    }

    return result;
  }, [collectionItems, globalFilters]);

  const gridDisplayItems = useMemo(() => {
    const result = [...analyticsFilteredItems];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const searched = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query)
          || (item.set && item.set.toLowerCase().includes(query))
      );
      return searched.sort((a, b) => {
        switch (sortBy) {
          case "value-desc":
            return parseCurrencyValue(b.valueLabel) - parseCurrencyValue(a.valueLabel);
          case "value-asc":
            return parseCurrencyValue(a.valueLabel) - parseCurrencyValue(b.valueLabel);
          case "name-asc":
            return a.name.localeCompare(b.name);
          case "name-desc":
            return b.name.localeCompare(a.name);
          default:
            return 0;
        }
      });
    }

    return result.sort((a, b) => {
      switch (sortBy) {
        case "value-desc":
          return parseCurrencyValue(b.valueLabel) - parseCurrencyValue(a.valueLabel);
        case "value-asc":
          return parseCurrencyValue(a.valueLabel) - parseCurrencyValue(b.valueLabel);
        case "name-asc":
          return a.name.localeCompare(b.name);
        case "name-desc":
          return b.name.localeCompare(a.name);
        default:
          return 0;
      }
    });
  }, [analyticsFilteredItems, searchQuery, sortBy]);

  const isEmpty = gridDisplayItems.length === 0 && !isLoading;
  const analyticsStats = useMemo(() => calculateCollectionStats(analyticsFilteredItems), [analyticsFilteredItems]);
  const handleSetAssetSpotlight = (asset) => {
    if (!asset?.id) return;
    router.push(`/account-settings?spotlightAssetId=${encodeURIComponent(String(asset.id))}#spotlight-asset`);
  };

  const globalActiveSelections = useMemo(() => {
    const selections = [];

    globalFilters.tcg
      .filter((tcg) => tcg !== "All")
      .forEach((tcg) => {
        selections.push({
          id: `tcg-${tcg}`,
          label: `TCG: ${tcg}`,
          onRemove: () => {
            setGlobalFilters((prev) => {
              const nextValues = prev.tcg.filter((value) => value !== tcg && value !== "All");
              return {
                ...prev,
                tcg: nextValues.length > 0 ? nextValues : ["All"],
              };
            });
          },
        });
      });

    ["set", "condition", "era", "binder"].forEach((key) => {
      (globalFilters[key] || []).forEach((value) => {
        selections.push({
          id: `${key}-${value}`,
          label: `${key.charAt(0).toUpperCase() + key.slice(1)}: ${value}`,
          onRemove: () => {
            setGlobalFilters((prev) => ({
              ...prev,
              [key]: (prev[key] || []).filter((entry) => entry !== value),
            }));
          },
        });
      });
    });

    if (globalFilters.assetType && globalFilters.assetType !== "all") {
      const selectedAssetType = filterOptions.assetType.find((option) => option.value === globalFilters.assetType);
      selections.push({
        id: `assetType-${globalFilters.assetType}`,
        label: `Asset Type: ${selectedAssetType?.label || globalFilters.assetType}`,
        onRemove: () => {
          setGlobalFilters((prev) => ({
            ...prev,
            assetType: "all",
          }));
        },
      });
    }

    return selections;
  }, [globalFilters, filterOptions.assetType]);

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
      <CollectionSectionLayout
        config={config}
        items={gridDisplayItems}
        isLoading={isLoading}
        isEmpty={isEmpty}
        onSearch={setSearchQuery}
        onFiltersChange={() => {}}
        onTypeFilterChange={handleTypeChipChange}
        selectedType={globalFilters.assetType}
        activeFilters={{}}
        onSortChange={setSortBy}
        onViewChange={setViewMode}
        showHeader={false}
        viewMode={viewMode}
        variant="detailed"
        showAdvancedFilters={false}
        showStats={false}
        stats={analyticsStats}
        leftSidebar={(
          <GlobalFilterPanel
            filters={globalFilters}
            options={filterOptions}
            onFilterChange={handleGlobalFilterChange}
            onClearAll={handleClearAllFilters}
            isLoading={isLoading}
          />
        )}
        contentAfterHeader={(
          <CollectionAnalyticsSurface
            items={analyticsFilteredItems}
            totalValue={analyticsStats.totalValue}
            investedValue={analyticsStats.investedValue}
          />
        )}
        extraActiveSelections={globalActiveSelections}
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
