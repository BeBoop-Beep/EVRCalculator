export interface PortfolioPerformancePoint {
  dateLabel: string;
  totalValue: number;
}

export interface PortfolioMover {
  id: string;
  name: string;
  changePercent7d: number;
  valueLabel: string;
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
