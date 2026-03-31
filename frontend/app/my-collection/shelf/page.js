"use client";

import { useState, useMemo } from "react";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import CollectionItemCard from "@/components/Profile/CollectionItemCard";
import { getSectionConfig } from "@/config/collectionSectionConfig";

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
  const config = getSectionConfig("shelf");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [view, setView] = useState("grid");

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
          const aVal = parseFloat(a.valueLabel || "0");
          const bVal = parseFloat(b.valueLabel || "0");
          return bVal - aVal;
        });
        break;
      case "value-asc":
        result.sort((a, b) => {
          const aVal = parseFloat(a.valueLabel || "0");
          const bVal = parseFloat(b.valueLabel || "0");
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

  return (
    <CollectionSectionLayout
      config={config}
      items={filteredAndSortedItems}
      isLoading={isLoading}
      isEmpty={isEmpty}
      renderItem={(item) => (
        <div className="h-full cursor-pointer transition-transform hover:scale-105">
          <CollectionItemCard item={item} variant="shelf" />
        </div>
      )}
      onSearch={setSearchQuery}
      onFiltersChange={setActiveFilters}
      onSortChange={setSortBy}
      onViewChange={setView}
      viewMode={view}
      emptyStateTitle="No sealed inventory"
      emptyStateDesc="Add sealed products to track your display and investment inventory."
    />
  );
}
