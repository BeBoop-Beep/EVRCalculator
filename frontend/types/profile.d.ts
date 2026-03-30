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
