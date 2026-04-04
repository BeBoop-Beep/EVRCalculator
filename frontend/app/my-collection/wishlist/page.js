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

// Mock data for wishlist
const MOCK_WISHLIST_ITEMS = [
  {
    id: "1",
    name: "Charizard ex Box",
    set: "Scarlet & Violet",
    productType: "Collection Box",
    imageUrl: null,
    valueLabel: "$54.99",
    priority: "high",
  },
  {
    id: "2",
    name: "Base Set Charizard",
    set: "Base Set",
    cardNumber: "004/102",
    imageUrl: null,
    valueLabel: "$3,500.00",
    priority: "high",
  },
  {
    id: "3",
    name: "Neo Genesis Booster Box",
    set: "Neo Genesis",
    productType: "Booster Box",
    imageUrl: null,
    valueLabel: "$199.99",
    priority: "medium",
  },
  {
    id: "4",
    name: "Pikachu Promo Card",
    set: "Promotional",
    cardNumber: "Pikachu-50",
    imageUrl: null,
    valueLabel: "$125.00",
    priority: "low",
  },
];

export default function MyCollectionWishlistSection() {
  const router = useRouter();
  const config = getSectionConfig("wishlist");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [view, setView] = useState("continuous");

  // Filter and sort items
  const filteredAndSortedItems = useMemo(() => {
    let result = [...MOCK_WISHLIST_ITEMS];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          (item.set && item.set.toLowerCase().includes(query))
      );
    }

    // Apply type filter
    if (activeFilters.type && activeFilters.type.length > 0) {
      result = result.filter((item) => {
        if (activeFilters.type.includes("cards")) return item.cardNumber;
        if (activeFilters.type.includes("sealed")) return item.productType;
        return false;
      });
    }

    // Apply priority filter
    if (activeFilters.priority && activeFilters.priority.length > 0) {
      result = result.filter((item) =>
        activeFilters.priority.includes(item.priority)
      );
    }

    // Apply sort
    switch (sortBy) {
      case "recent":
        // Keep default order
        break;
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
      default:
        // priority: sort by priority order
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        result.sort(
          (a, b) =>
            (priorityOrder[a.priority] || 999) - (priorityOrder[b.priority] || 999)
        );
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
      variant="detailed"
      onSetAssetSpotlight={handleSetAssetSpotlight}
      showAddAction
      onAddCard={handleAddCard}
      onAddSealedProduct={handleAddSealedProduct}
      onImportCollection={handleImportCollection}
      emptyStateTitle="No wishlist items"
      emptyStateDesc="Add items to your wishlist to track things you'd like to collect."
    />
  );
}
