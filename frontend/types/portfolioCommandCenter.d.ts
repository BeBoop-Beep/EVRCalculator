export interface PortfolioMetricCard {
  id: string;
  label: string;
  value: string;
  subValue?: string;
  hint?: string;
  valueTone?: "positive" | "negative" | "neutral";
  badge?: string;
  badgeTone?: "positive" | "negative" | "warning" | "neutral";
}

export interface PortfolioCommandCenterData {
  totalValue: number;
  investedValue?: number;
  change24hPercent: number;
  change7dPercent: number;
  cardsCount: number;
  sealedCount: number;
  wishlistCount: number;
  lastSyncedAt: string;
  freshnessLabel: string;
}
