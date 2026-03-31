/**
 * Centralized configuration for My Collection sections
 * Defines metadata, features, filters, and sorting for each section
 * Allows sections to stay consistent while supporting purpose-specific behavior
 */

export const sectionConfigs = {
  collection: {
    id: "collection",
    slug: "collection",
    title: "My Collection",
    eyebrow: "Manage Collection",
    subtitle: "Add, edit, import, and organize your owned collection.",
    description: "Master view of all your owned assets across cards, sealed, and merchandise.",
    
    // Feature flags - what controls to show
    supportsSearch: true,
    supportsFilters: true,
    supportsSorting: true,
    supportsViewToggle: true,
    defaultView: "grid", // "grid" or "list"
    
    // Filter definitions
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
    
    // Sort options
    sortOptions: [
      { id: "recent", label: "Recently Added" },
      { id: "value-desc", label: "Value (High to Low)" },
      { id: "value-asc", label: "Value (Low to High)" },
      { id: "name-asc", label: "Name (A–Z)" },
      { id: "name-desc", label: "Name (Z–A)" },
      { id: "condition", label: "Condition" },
    ],
    defaultSort: "recent",
  },

  binder: {
    id: "binder",
    slug: "binder",
    title: "My Binder",
    eyebrow: "Manage Binder",
    subtitle: "Build and rearrange binder pages privately.",
    description: "Visual card organization: view, curate, and arrange cards by set and rarity.",
    
    // Binder is card-focused; disable view toggle to keep it grid-only
    supportsSearch: true,
    supportsFilters: true,
    supportsSorting: true,
    supportsViewToggle: false,
    defaultView: "grid",
    
    filters: [
      {
        id: "set",
        label: "Set",
        type: "select",
        options: [], // Dynamically populated from user's collections
      },
      {
        id: "rarity",
        label: "Rarity",
        type: "select",
        options: [
          { id: "common", label: "Common" },
          { id: "uncommon", label: "Uncommon" },
          { id: "rare", label: "Rare" },
          { id: "holo-rare", label: "Holo Rare" },
          { id: "ex", label: "EX" },
        ],
      },
      {
        id: "foil",
        label: "Special",
        type: "checkbox",
        options: [
          { id: "foil", label: "Foil/Reverse Holo" },
        ],
      },
    ],
    
    sortOptions: [
      { id: "set-name", label: "Set, then Name" },
      { id: "rarity", label: "Rarity" },
      { id: "name-asc", label: "Name (A–Z)" },
      { id: "value-desc", label: "Value (High to Low)" },
    ],
    defaultSort: "set-name",
  },

  shelf: {
    id: "shelf",
    slug: "shelf",
    title: "My Shelf",
    eyebrow: "Manage Shelf",
    subtitle: "Track sealed inventory and display placements.",
    description: "Sealed products and display items: booster boxes, tins, cases, and more.",
    
    supportsSearch: true,
    supportsFilters: true,
    supportsSorting: true,
    supportsViewToggle: true,
    defaultView: "grid",
    
    filters: [
      {
        id: "productType",
        label: "Product Type",
        type: "select",
        options: [
          { id: "booster-box", label: "Booster Box" },
          { id: "booster-pack", label: "Booster Pack" },
          { id: "tin", label: "Tin" },
          { id: "collection-box", label: "Collection Box" },
          { id: "case", label: "Case" },
          { id: "other", label: "Other" },
        ],
      },
      {
        id: "condition",
        label: "Condition",
        type: "select",
        options: [
          { id: "sealed", label: "Sealed" },
          { id: "opened", label: "Opened" },
          { id: "damaged", label: "Damaged" },
        ],
      },
    ],
    
    sortOptions: [
      { id: "recent", label: "Recently Added" },
      { id: "value-desc", label: "Value (High to Low)" },
      { id: "value-asc", label: "Value (Low to High)" },
      { id: "name-asc", label: "Name (A–Z)" },
      { id: "product-type", label: "Product Type" },
    ],
    defaultSort: "recent",
  },

  wishlist: {
    id: "wishlist",
    slug: "wishlist",
    title: "My Wishlist",
    eyebrow: "Manage Wishlist",
    subtitle: "Track targets, priorities, and acquisition plans.",
    description: "Wanted items: cards, sealed products, and more on your collection radar.",
    
    supportsSearch: true,
    supportsFilters: true,
    supportsSorting: true,
    supportsViewToggle: true,
    defaultView: "grid",
    
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
        id: "priority",
        label: "Priority",
        type: "select",
        options: [
          { id: "high", label: "High" },
          { id: "medium", label: "Medium" },
          { id: "low", label: "Low" },
        ],
      },
    ],
    
    sortOptions: [
      { id: "priority", label: "Priority" },
      { id: "recent", label: "Recently Added" },
      { id: "value-desc", label: "Est. Value (High to Low)" },
      { id: "value-asc", label: "Est. Value (Low to High)" },
      { id: "name-asc", label: "Name (A–Z)" },
    ],
    defaultSort: "priority",
  },
};

/**
 * Get configuration for a specific section
 * @param {string} sectionId - The section identifier (collection, binder, shelf, wishlist)
 * @returns {object} The section configuration object
 */
export function getSectionConfig(sectionId) {
  const config = sectionConfigs[sectionId];
  if (!config) {
    throw new Error(`Unknown collection section: ${sectionId}`);
  }
  return config;
}

/**
 * Get all available sections
 * @returns {array} Array of section configuration objects
 */
export function getAllSections() {
  return Object.values(sectionConfigs);
}
