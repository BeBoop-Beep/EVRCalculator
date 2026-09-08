export function describeRelativePerformance(timeframe, leaderLabel, leaderReturn, laggardLabel, laggardReturn) {
  const spread = Number(leaderReturn) - Number(laggardReturn);
  return `Over ${timeframe}, ${leaderLabel} returned ${Number(leaderReturn).toFixed(1)}%, versus ${Number(laggardReturn).toFixed(1)}% for ${laggardLabel} â€” a ${spread.toFixed(1)} percentage-point difference.`;
}
