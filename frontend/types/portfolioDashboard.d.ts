export interface PortfolioPerformancePoint {
  dateLabel: string;
  totalValue: number;
}

export interface PortfolioRangeSeries {
  points: PortfolioPerformancePoint[];
  helper?: string;
  investedValue?: number;
  totalInvested?: number;
  totalProfit?: number;
  roiPercent?: number;
  changeDollar?: number;
  changePercent?: number;
}

export interface PortfolioPerformanceData {
  periodLabel?: string;
  points?: PortfolioPerformancePoint[];
  rangeSeries?: Partial<Record<"7D" | "1M" | "6M" | "1Y" | "LT", PortfolioRangeSeries>>;
}

export interface PortfolioMover {
  id: string;
  name: string;
  changePercent7d: number;
  dollarImpact?: number;
}

export interface AllocationSlice {
  id: string;
  label: string;
  valuePercent: number;
  valueLabel: string;
}

export interface PortfolioInsightsData {
  topMovers: PortfolioMover[];
  allocationSummary: AllocationSlice[];
  concentrationText: string;
}
