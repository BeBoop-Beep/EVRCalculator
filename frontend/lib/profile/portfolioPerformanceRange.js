export const PERFORMANCE_TIME_RANGES = ["7D", "1M", "6M", "1Y"];

const PERFORMANCE_SERIES = {
  "7D": {
    helper: "Best weekly run in 2 months",
    points: [
      { dateLabel: "Mar 24", totalValue: 17120 },
      { dateLabel: "Mar 25", totalValue: 17385 },
      { dateLabel: "Mar 26", totalValue: 17640 },
      { dateLabel: "Mar 27", totalValue: 17530 },
      { dateLabel: "Mar 28", totalValue: 17825 },
      { dateLabel: "Mar 29", totalValue: 18080 },
      { dateLabel: "Mar 30", totalValue: 18170 },
      { dateLabel: "Mar 31", totalValue: 18245 },
    ],
  },
  "1M": {
    helper: "Momentum accelerated through the second half of the month",
    points: [
      { dateLabel: "Wk 1", totalValue: 16740 },
      { dateLabel: "Wk 2", totalValue: 16910 },
      { dateLabel: "Wk 3", totalValue: 17285 },
      { dateLabel: "Wk 4", totalValue: 17860 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
  "6M": {
    helper: "Steady upside driven by sealed strength and premium singles",
    points: [
      { dateLabel: "Oct", totalValue: 14980 },
      { dateLabel: "Nov", totalValue: 15320 },
      { dateLabel: "Dec", totalValue: 15890 },
      { dateLabel: "Jan", totalValue: 16540 },
      { dateLabel: "Feb", totalValue: 17440 },
      { dateLabel: "Mar", totalValue: 18245 },
    ],
  },
  "1Y": {
    helper: "Long-term appreciation remains intact across the full portfolio",
    points: [
      { dateLabel: "Q2", totalValue: 13220 },
      { dateLabel: "Q3", totalValue: 14480 },
      { dateLabel: "Q4", totalValue: 15670 },
      { dateLabel: "Q1", totalValue: 17040 },
      { dateLabel: "Now", totalValue: 18245 },
    ],
  },
};

export function getPerformanceRangeData(selectedRange, performanceData) {
  const range = PERFORMANCE_SERIES[selectedRange] ? selectedRange : "7D";
  const baseSeries = PERFORMANCE_SERIES[range];
  const overrideSeries = performanceData?.rangeSeries?.[range];
  const points = overrideSeries?.points?.length
    ? overrideSeries.points
    : range === "7D" && performanceData?.points?.length
      ? performanceData.points
      : baseSeries.points;

  const currentValue = points[points.length - 1]?.totalValue || 0;
  const startValue = points[0]?.totalValue || 0;
  const changeDollar = currentValue - startValue;
  const changePercent = startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0;

  return {
    range,
    helper: overrideSeries?.helper || baseSeries.helper,
    points,
    currentValue,
    changeDollar,
    changePercent,
  };
}