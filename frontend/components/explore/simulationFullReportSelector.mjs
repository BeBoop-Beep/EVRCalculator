import { resolveCanonicalFinancialRip } from "./financialRipV3Selector.mjs";
import { formatMetricCurrency, formatMetricNumber, formatMetricProbability, formatMetricRatio } from "./simulationMetricsDisplay.mjs";
import { firstFiniteField, selectPercentileValue, toFiniteNumber } from "./simulationMetricsSelector.mjs";

const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const camel = (value) => String(value).replace(/_([a-z])/g, (_match, letter) => letter.toUpperCase());
const raw = (financial, key) => object(object(object(financial?.components)[key] ?? object(financial?.components)[camel(key)]).raw);

function row(key, label, value, format, classification, help = null) {
  const numericValue = toFiniteNumber(value);
  return numericValue === null ? null : { key, label, value: format(numericValue), classification, help };
}
function group(key, title, classification, rows) {
  const available = rows.filter(Boolean);
  return available.length ? { key, title, classification, rows: available } : null;
}

// Explicit public allowlist: unknown keys, seeds, weights, anchors, and run
// metadata are unreachable. Selection and display formatting are the only work.
export function selectSimulationFullReport({ canonical, summary = {}, percentiles = [] } = {}) {
  const financial = object(resolveCanonicalFinancialRip(canonical));
  const trueWin = raw(financial, "true_win_frequency");
  const typical = raw(financial, "typical_value_retention");
  const loss = raw(financial, "loss_resilience");
  const realistic = raw(financial, "realistic_upside");
  const jackpot = raw(financial, "jackpot_upside");
  const base = raw(financial, "base_economic_efficiency");
  const disclosures = object(financial.distributionDisclosures);
  const depth = object(financial.depthAndRobustness);
  const percentile = (point) => selectPercentileValue(percentiles, point / 100);
  const money = formatMetricCurrency;
  const groups = [
    group("typical", "Typical Outcomes", "Financial RIP evidence", [
      row("expectedValue", "Expected Value", firstFiniteField(summary, ["mean_value", "meanValue"]), money, "Financial RIP evidence"),
      row("typicalOpening", "Typical Opening", percentile(50) ?? firstFiniteField(summary, ["median_value", "medianValue"]) ?? typical.typicalPackValue, money, "Financial RIP evidence", "P50, or median, modeled opening value."),
      row("p25", "P25", percentile(25), money, "Additional diagnostic"),
      row("p75", "P75", percentile(75), money, "Additional diagnostic"),
      row("typicalRetention", "Typical Retention vs Cost", typical.typicalRetentionRatio, formatMetricRatio, "Financial RIP evidence"),
    ]),
    group("downside", "Downside", "Financial RIP evidence", [
      row("chanceToBeatCost", "Chance to Beat Cost", firstFiniteField(summary, ["prob_profit", "probProfit"]) ?? trueWin.trueWinProbability, formatMetricProbability, "Financial RIP evidence"),
      row("averageLosingReturn", "Average Losing Return", loss.averageLosingReturnValue, money, "Financial RIP evidence"),
      row("lossRetention", "Retention When Losing", loss.averageRetentionGivenLoss, formatMetricProbability, "Financial RIP evidence"),
      row("badFloor", "Bad Floor", percentile(5) ?? firstFiniteField(summary, ["tail_value_p05", "tailValueP05"]) ?? disclosures.p05Value, money, "Additional diagnostic", "P05: only 5% of modeled openings finish below this value."),
      row("hardLossProbability", "Hard-Loss Probability", loss.hardLossProbability, formatMetricProbability, "Financial RIP evidence", "Chance of recovering less than half of pack cost."),
      row("nearMissShare", "Near-Miss Share of Losing Packs", loss.softLossShareGivenLoss, formatMetricProbability, "Financial RIP evidence"),
    ]),
    group("upside", "Upside & Tail", "Financial RIP evidence", [
      row("strongUpside", "Strong Upside", percentile(95) ?? realistic.p95ThresholdValue, money, "Financial RIP evidence", "P95: threshold reached by the strongest 5% of modeled openings."),
      row("jackpotUpside", "Jackpot Upside", percentile(99) ?? jackpot.p99ThresholdValue, money, "Financial RIP evidence", "P99: threshold reached by the top 1% of modeled openings."),
      row("realisticTailMean", "Average Return, 95th–99th Percentile", realistic.realisticTailMeanValue, money, "Financial RIP evidence"),
      row("jackpotTailMean", "Average Top-1% Return", jackpot.jackpotTailMeanValue, money, "Financial RIP evidence"),
      row("bestPull", "Best Simulated Pull", firstFiniteField(summary, ["max_value", "maxValue"]), money, "Additional diagnostic"),
      row("jackpotValueShare", "Jackpot Value Share", jackpot.jackpotValueShare ?? base.jackpotValueShare, formatMetricProbability, "Financial RIP evidence", "Share of total modeled value produced by top-1% outcomes."),
    ]),
    group("diagnostics", "Economic / Distribution Diagnostics", "Additional diagnostic", [
      row("totalRtp", "Total RTP", base.totalRtpRatio, formatMetricProbability, "Financial RIP evidence", "Return to player: modeled Expected Value as a share of pack cost."),
      row("baseRtp", "RTP Excluding Top 1%", base.baseRtpExcludingTop1Pct, formatMetricProbability, "Financial RIP evidence", "Modeled return after removing top-1% outcomes."),
      row("volatility", "Outcome Volatility", firstFiniteField(summary, ["coefficient_of_variation", "coefficientOfVariation"]), formatMetricNumber, "Additional diagnostic"),
      row("concentration", "EV Concentration", depth.hhiEvConcentration ?? firstFiniteField(summary, ["hhi_ev_concentration", "hhiEvConcentration"]), formatMetricNumber, "Additional diagnostic"),
      row("effectiveChases", "Effective Chase Count", depth.effectiveChaseCount ?? firstFiniteField(summary, ["effective_chase_count", "effectiveChaseCount"]), (value) => formatMetricNumber(value, 1), "Additional diagnostic"),
    ]),
  ].filter(Boolean);
  const rowCount = groups.reduce((count, item) => count + item.rows.length, 0);
  return { available: rowCount >= 3, groups };
}
