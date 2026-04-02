/**
 * Unified collection view system configuration
 * Defines shared view modes, grid layouts, and responsive breakpoints
 * Used by both My Collection (owner mode) and Public Collection (public mode)
 */

export const VIEW_MODES = {
  CONTINUOUS: {
    id: "continuous",
    label: "Continuous Scroll",
    description: "Browse all items with continuous scrolling",
    icon: "grid",
  },
  BINDER: {
    id: "binder",
    label: "Binder Pages",
    description: "View cards organized in fixed-page binder format",
    icon: "pages",
  },
};

export const GRID_LAYOUT = {
  CONTINUOUS_SCROLL: {
    viewMode: "continuous",
    // Desktop: 4 cards across
    colsDesktop: 4,
    // Tablet: 2 cards across
    colsTablet: 2,
    // Mobile: 2 cards across
    colsMobile: 2,
    gapClass: "gap-4",
    // Responsive grid classes
    gridClasses: "grid grid-cols-2 gap-4 lg:grid-cols-4",
  },
  BINDER_PAGE: {
    viewMode: "binder",
    // Desktop: 4 cards across in binder
    colsDesktop: 4,
    // Tablet: 2 cards across
    colsTablet: 2,
    // Mobile: 2 cards across
    colsMobile: 2,
    // Fixed 3 rows per page on desktop = 12 cards per page
    rowsPerPageDesktop: 3,
    cardsPerPageDesktop: 12,
    gapClass: "gap-4",
    gridClasses: "grid grid-cols-2 gap-4 lg:grid-cols-4",
    // Pagination controls
    showPageNavigation: true,
    showPageInfo: true,
  },
};

export const CARD_SIZING = {
  // Standardized across both views
  imageAspectRatio: "3 / 4",
  compactHeight: "min-h-[280px]",
  detailedHeight: "min-h-[320px]",
};

export const RESPONSIVE_BREAKPOINTS = {
  sm: "640px",
  md: "768px",
  lg: "1024px",
  xl: "1280px",
};

/**
 * Helper: Get grid classes for a specific view mode and context
 */
export function getGridClasses(viewMode = "continuous") {
  const layout = viewMode === "binder" ? GRID_LAYOUT.BINDER_PAGE : GRID_LAYOUT.CONTINUOUS_SCROLL;
  return layout.gridClasses;
}

/**
 * Helper: Calculate items per page for binder mode
 */
export function getBinderPageSize(viewMode = "binder") {
  if (viewMode !== "binder") return Infinity;
  const layout = GRID_LAYOUT.BINDER_PAGE;
  return layout.cardsPerPageDesktop;
}

/**
 * Helper: Get hover interaction classes (shared between views)
 */
export const HOVER_INTERACTION = {
  scale: "hover:scale-105",
  glow: "hover:shadow-lg",
  combined: "transition-transform duration-300 hover:scale-105",
};
