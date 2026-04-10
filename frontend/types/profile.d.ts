export interface TcgOption {
  id: number | string;
  name: string;
}

export interface UserProfileRow {
  id: string;
  email: string;
  username: string | null;
  display_name: string | null;
  bio: string | null;
  avatar_url: string | null;
  location: string | null;
  favorite_tcg_id: number | string | null;
  favorite_tcg_name: string | null;
  is_profile_public: boolean | null;
  show_portfolio_value: boolean | null;
  show_activity: boolean | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PortfolioSnapshot {
  totalCollectionValue: number | null;
  cardsOwned: number | null;
  sealedProductsOwned: number | null;
  costBasis: number | null;
  profitLoss: number | null;
}

export interface ProfileResponse {
  profile: UserProfileRow;
}

export interface PublicCollectionSummary {
  portfolio_value: number | null;
  cards_count: number | null;
  sealed_count: number | null;
  graded_count: number | null;
  portfolio_delta_1d: number | null;
  portfolio_delta_7d: number | null;
  portfolio_delta_3m: number | null;
  portfolio_delta_6m: number | null;
  portfolio_delta_1y: number | null;
  portfolio_delta_lifetime: number | null;
  portfolio_delta_pct_1d: number | null;
  portfolio_delta_pct_7d: number | null;
  portfolio_delta_pct_3m: number | null;
  portfolio_delta_pct_6m: number | null;
  portfolio_delta_pct_1y: number | null;
  portfolio_delta_pct_lifetime: number | null;
}

export interface CollectionItemDTO {
  id: string;
  collectible_type: "card" | "sealed_product" | "graded_card" | "merchandise";
  collectible_id: number | string | null;
  quantity: number;
  name: string;
  set_name: string | null;
  card_number: string | null;
  rarity: string | null;
  condition: string | null;
  printing_type: string | null;
  edition: string | null;
  special_type: string | null;
  estimated_value: number;
  image_url: string;
  image_large_url: string;
  image_type?: "card" | "graded_base_card" | "sealed" | "fallback";
  image_source?: "card_variant" | "card" | "graded_linked_card_variant" | "graded_linked_card" | "sealed_product" | "fallback";
  source_confidence?: "high" | "medium" | "low";
}

export interface PublicCollectionSummaryResponse {
  collection_summary: PublicCollectionSummary;
  collection_items?: CollectionItemDTO[];
}

export interface PublicUserProfile {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  is_profile_public: boolean | null;
  location: string | null;
  favorite_tcg_id: number | string | null;
  favorite_tcg_name: string | null;
  created_at: string | null;
  collection_summary: PublicCollectionSummary | null;
  collection_summary_warning: string | null;
}

export interface PublicProfileResponse {
  profile: PublicUserProfile;
}

export interface ProfileUpdatePayload {
  display_name?: string;
  bio?: string;
  location?: string;
  favorite_tcg_id?: number | string | null;
  is_profile_public?: boolean;
  show_portfolio_value?: boolean;
  show_activity?: boolean;
}

export interface ProfileDataError {
  message: string;
  status: number;
  code?: string;
}

export interface ProfileDataResult<T> {
  data: T;
  error: ProfileDataError | null;
}

export interface PublicProfileTabItem {
  label: string;
  href: string;
  exact?: boolean;
}

export interface PublicShowcaseAsset {
  id: string;
  name: string;
  context: string;
  valueLabel: string;
  imageUrl: string | null;
  slotKey: "topConviction" | "biggestGainer" | "spotlight";
  category: string;
  categoryIcon: string;
  slotMode: "computed" | "manual";
  isUserSelected?: boolean;
  usedFallback?: boolean;
  spotlightFallbackSource?: string | null;
  hasPerformanceData?: boolean;
}

// Backward-compatible aliases for older naming.
export type PublicFeaturedItem = PublicShowcaseAsset;
export type PublicShowcaseItem = PublicShowcaseAsset;

export interface PublicShowcaseSlots {
  topConviction: PublicShowcaseAsset | null;
  biggestGainer: PublicShowcaseAsset | null;
  spotlight: PublicShowcaseAsset | null;
}

export interface PublicPortfolioStat {
  id: string;
  label: string;
  value: string;
  helpText?: string;
}

export interface PublicPortfolioPerformance {
  points: number[];
  periodLabel: string;
  valueLabel: string;
  trendLabel: string;
  returnLabel: string;
}

export interface PublicPortfolioHighlight {
  id: string;
  label: string;
  value: string;
  context?: string;
}

export interface PublicRecentActivityItem {
  id: string;
  title: string;
  description: string;
  timestampLabel: string;
}

export interface PublicProfileOverviewModel {
  showcase: PublicShowcaseSlots;
  snapshotStats: PublicPortfolioStat[];
  performance: PublicPortfolioPerformance;
  highlights: PublicPortfolioHighlight[];
  recentActivity: PublicRecentActivityItem[];
}
