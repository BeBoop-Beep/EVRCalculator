"use client";

import { useState, useMemo } from "react";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import CollectionItemCard from "@/components/Profile/CollectionItemCard";
import { getSectionConfig } from "@/config/collectionSectionConfig";

// Mock data for demonstration
const MOCK_ITEMS = [
  {
    id: "1",
    name: "Pikachu ex",
    set: "Scarlet & Violet",
    cardNumber: "025/102",
    condition: "Near Mint",
    imageUrl: null,
    valueLabel: "$45.50",
    isFoil: false,
  },
  {
    id: "2",
    name: "Charizard ex",
    set: "Scarlet & Violet",
    cardNumber: "003/102",
    condition: "Mint",
    imageUrl: null,
    valueLabel: "$120.00",
    isFoil: true,
  },
  {
    id: "3",
    name: "Booster Box - Scarlet & Violet",
    set: "Scarlet & Violet",
    productType: "Booster Box",
    condition: "Sealed",
    imageUrl: null,
    valueLabel: "$89.99",
  },
  {
    id: "4",
    name: "Blastoise",
    set: "Base Set",
    cardNumber: "002/102",
    condition: "Lightly Played",
    imageUrl: null,
    valueLabel: "$15.00",
  },
];

export default function MyCollectionSection() {
  const config = getSectionConfig("collection");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);

  // Filter and sort items
  const filteredAndSortedItems = useMemo(() => {
    let result = [...MOCK_ITEMS];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          (item.set && item.set.toLowerCase().includes(query))
      );
    }

    // Apply type filter if active
    if (activeFilters.type && activeFilters.type.length > 0) {
      result = result.filter((item) => {
        if (activeFilters.type.includes("cards")) return item.cardNumber;
        if (activeFilters.type.includes("sealed")) return item.productType;
        return false;
      });
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
      case "name-asc":
        result.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "name-desc":
        result.sort((a, b) => b.name.localeCompare(a.name));
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
          <CollectionItemCard
            item={item}
            variant={item.cardNumber ? "detailed" : "shelf"}
          />
        </div>
      )}
      onSearch={setSearchQuery}
      onFiltersChange={setActiveFilters}
      onSortChange={setSortBy}
      onViewChange={(view) => {
        /* Handle view change */
      }}
      emptyStateTitle="No collection items yet"
      emptyStateDesc="Start by adding cards, sealed products, or other items to your collection."
    />
  );
}
