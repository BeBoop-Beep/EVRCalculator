"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import { getSectionConfig } from "@/config/collectionSectionConfig";

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

// Mock data for shelf (sealed products)
const MOCK_SHELF_ITEMS = [
  {
    id: "1",
    name: "Scarlet & Violet Booster Box",
    productType: "Booster Box",
    set: "Scarlet & Violet",
    condition: "Sealed",
    imageUrl: null,
    valueLabel: "$89.99",
    quantity: 1,
  },
  {
    id: "2",
    name: "Base Set Booster Box",
    productType: "Booster Box",
    set: "Base Set",
    condition: "Opened",
    imageUrl: null,
    valueLabel: "$450.00",
    quantity: 1,
  },
  {
    id: "3",
    name: "Scarlet & Violet Premium Collection",
    productType: "Collection Box",
    set: "Scarlet & Violet",
    condition: "Sealed",
    imageUrl: null,
    valueLabel: "$24.99",
    quantity: 2,
  },
  {
    id: "4",
    name: "Black & White Booster Tin",
    productType: "Tin",
    set: "Black & White",
    condition: "Sealed",
    imageUrl: null,
    valueLabel: "$35.00",
    quantity: 1,
  },
];

export default function MyCollectionShelfSection() {
  const router = useRouter();
  const config = getSectionConfig("shelf");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [view, setView] = useState("continuous");

  // Filter and sort items
  const filteredAndSortedItems = useMemo(() => {
    let result = [...MOCK_SHELF_ITEMS];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          (item.set && item.set.toLowerCase().includes(query))
      );
    }

    // Apply product type filter
    if (activeFilters.productType && activeFilters.productType.length > 0) {
      result = result.filter((item) =>
        activeFilters.productType.includes(item.productType)
      );
    }

    // Apply condition filter
    if (activeFilters.condition && activeFilters.condition.length > 0) {
      result = result.filter((item) =>
        activeFilters.condition.includes(item.condition)
      );
    }

    // Apply sort
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
      case "product-type":
        result.sort((a, b) => a.productType.localeCompare(b.productType));
        break;
      default:
        // recent (default order)
        break;
    }

    return result;
  }, [searchQuery, activeFilters, sortBy]);

  const isEmpty = filteredAndSortedItems.length === 0 && !isLoading;
  const handleSetAssetSpotlight = (asset) => {
    if (!asset?.id) return;
    router.push(`/account-settings?spotlightAssetId=${encodeURIComponent(String(asset.id))}#spotlight-asset`);
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
    <CollectionSectionLayout
      config={config}
      items={filteredAndSortedItems}
      isLoading={isLoading}
      isEmpty={isEmpty}
      onSearch={setSearchQuery}
      onFiltersChange={setActiveFilters}
      onSortChange={setSortBy}
      showHeader={false}
      onViewChange={setView}
      viewMode={view}
      variant="shelf"
      onSetAssetSpotlight={handleSetAssetSpotlight}
      showAddAction
      onAddCard={handleAddCard}
      onAddSealedProduct={handleAddSealedProduct}
      onImportCollection={handleImportCollection}
      emptyStateTitle="No sealed inventory"
      emptyStateDesc="Add sealed products to track your display and investment inventory."
    />
  );
}
