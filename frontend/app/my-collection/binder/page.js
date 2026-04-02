"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import CollectionSectionLayout from "@/components/Profile/CollectionSectionLayout";
import { getSectionConfig } from "@/config/collectionSectionConfig";

// Mock data for binder (cards only)
const MOCK_BINDER_ITEMS = [
  {
    id: "1",
    name: "Pikachu ex",
    set: "Scarlet & Violet",
    cardNumber: "025/102",
    condition: "Near Mint",
    imageUrl: null,
    valueLabel: "$45.50",
    isFoil: false,
    rarity: "holo-rare",
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
    rarity: "holo-rare",
  },
  {
    id: "3",
    name: "Blastoise",
    set: "Base Set",
    cardNumber: "002/102",
    condition: "Lightly Played",
    imageUrl: null,
    valueLabel: "$15.00",
    isFoil: false,
    rarity: "rare",
  },
  {
    id: "4",
    name: "Dragonite",
    set: "Base Set",
    cardNumber: "004/102",
    condition: "Near Mint",
    imageUrl: null,
    valueLabel: "$28.00",
    isFoil: true,
    rarity: "holo-rare",
  },
];

export default function MyCollectionBinderSection() {
  const router = useRouter();
  const config = getSectionConfig("binder");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [sortBy, setSortBy] = useState(config.defaultSort);

  // Filter and sort items
  const filteredAndSortedItems = useMemo(() => {
    let result = [...MOCK_BINDER_ITEMS];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          (item.set && item.set.toLowerCase().includes(query)) ||
          (item.cardNumber && item.cardNumber.includes(query))
      );
    }

    // Apply rarity filter
    if (activeFilters.rarity && activeFilters.rarity.length > 0) {
      result = result.filter((item) =>
        activeFilters.rarity.includes(item.rarity)
      );
    }

    // Apply foil filter
    if (activeFilters.foil && activeFilters.foil.length > 0) {
      result = result.filter((item) => item.isFoil);
    }

    // Apply sort
    switch (sortBy) {
      case "rarity":
        result.sort((a, b) => a.rarity.localeCompare(b.rarity));
        break;
      case "name-asc":
        result.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "value-desc":
        result.sort((a, b) => {
          const aVal = parseFloat(a.valueLabel || "0");
          const bVal = parseFloat(b.valueLabel || "0");
          return bVal - aVal;
        });
        break;
      default:
        // set-name: default order
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
      onViewChange={() => {
        /* Binder doesn't support view toggle */
      }}
      viewMode="binder"
      variant="detailed"
      onSetAssetSpotlight={handleSetAssetSpotlight}
      showAddAction
      onAddCard={handleAddCard}
      onAddSealedProduct={handleAddSealedProduct}
      onImportCollection={handleImportCollection}
      emptyStateTitle="No cards in binder"
      emptyStateDesc="Add cards to your binder to start organizing your collection."
    />
  );
}
