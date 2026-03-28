"use client";
import { useState, useEffect, useMemo } from "react";
import ProductStoreFilter from "../ProductStoreFilter/ProductStoreFilter";

export default function ProductStoreFilterWrapper({ onFilterChange, categories }) {
  const [selectedChildCategories, setSelectedChildCategories] = useState([]);
  const [expandedParents, setExpandedParents] = useState([]);

  // Filter out the "Merchandise" parent category
  const filteredParents = useMemo(() => {
    return categories.filter(
      (category) => !category.parent && category.name !== "Merchandise"
    );
  }, [categories]);

  const children = useMemo(() => categories.filter((category) => category.parent), [categories]);

  const groupedChildren = useMemo(() => {
    return children.reduce((acc, category) => {
      if (!acc[category.parent]) {
        acc[category.parent] = [];
      }
      acc[category.parent].push(category);
      return acc;
    }, {});
  }, [children]);

  // Handle child category selection
  const handleChildCategorySelect = (childId) => {
    setSelectedChildCategories((prevSelected) => {
      if (prevSelected.includes(childId)) {
        return prevSelected.filter((id) => id !== childId); // Deselect
      } else {
        return [...prevSelected, childId]; // Select
      }
    });
  };

  // Handle parent category expand/collapse
  const toggleParent = (parentId) => {
    setExpandedParents((prevExpanded) =>
      prevExpanded.includes(parentId)
        ? prevExpanded.filter((id) => id !== parentId) // Collapse
        : [...prevExpanded, parentId] // Expand
    );
  };

  // Clear all selected filters (without collapsing parents)
  const handleClearAllFilters = () => {
    setSelectedChildCategories([]);
  };

  // Notify parent component (Products) when selected child categories change
  useEffect(() => {
    onFilterChange(selectedChildCategories);
  }, [selectedChildCategories, onFilterChange]);

  return (
    <ProductStoreFilter
      categories={categories}
      parents={filteredParents} // Pass the filtered parent categories
      expandedParents={expandedParents}
      groupedChildren={groupedChildren}
      selectedChildCategories={selectedChildCategories}
      toggleParent={toggleParent}
      onChildCategorySelect={handleChildCategorySelect}
      onClearAllFilters={handleClearAllFilters}
    />
  );
}