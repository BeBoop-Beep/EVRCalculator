/**
 * Interpretability Configuration for RIP Statistics Dashboard
 *
 * This file provides user-friendly explanations, insights, and label mappings
 * that enhance dashboard clarity without changing underlying calculations.
 *
 * It reuses the existing RANK_CONFIG tier system and extends it with:
 * - Tier-based insights (e.g., "Strong value profile")
 * - Friendly metric labels
 * - Tooltip explanations for metrics and scores
 */

import { RANK_CONFIG } from "./rankConfig";

/**
 * Pack Score interpretation based on tier/rank.
 * Used to render a brief insight line under the Pack Rank badge.
 */
export const PACK_SCORE_INSIGHTS = {
  S: {
    label: "Elite",
    insight: "Elite value profile — strongest overall rip profile among tracked sets.",
  },
  A: {
    label: "Strong",
    insight: "Strong value profile — favorable score with manageable tradeoffs.",
  },
  B: {
    label: "Good",
    insight: "Good profile — useful upside, but not without risk.",
  },
  C: {
    label: "Mixed",
    insight: "Mixed profile — some upside, but tradeoffs are meaningful.",
  },
  D: {
    label: "Weak",
    insight: "Weak profile — risk and loss pressure outweigh most upside.",
  },
  F: {
    label: "Poor",
    insight: "Poor profile — unfavorable rip profile based on current inputs.",
  },
  F2F: {
    label: "Poor",
    insight: "Poor profile — unfavorable rip profile based on current inputs.",
  },
  null: {
    label: "Unknown",
    insight: "Profile assessment unavailable.",
  },
};

/**
 * Friendly display labels for metrics.
 * Maps raw metric field/label names to user-friendly display labels.
 * Keyed by category (Profit/Safety/Stability/Advanced).
 */
export const FRIENDLY_METRIC_LABELS = {
  // Profit card
  "Probability of Profit": "Chance to Beat Pack Cost",
  "Chance to Beat Pack Cost": "Chance to Beat Pack Cost",
  "EV / Mean Value": "Expected Value",
  "Median-to-Cost Ratio": "Typical Return",
  "P95-to-Cost Ratio": "Big Hit Upside",
  "P95 Value / Cost Ratio": "Big Hit Upside",
  "P99-to-Cost Ratio": "God Pull Upside",
  "P99 Value / Cost Ratio": "God Pull Upside",
  ROI: "Return on Investment",
  "Pack Cost": "Pack Market Price",
  "Average Pack Value": "Expected Value",
  "Current Pack Cost": "Pack Market Price",
  "Average Loss": "Average Loss",
  "Chance at a Big Pull": "Chance at a Big Pull",

  // Safety card
  "Expected Loss When Losing / Cost": "Average Loss When You Miss vs Cost",
  "Median Loss When Losing / Cost": "Typical Loss vs Cost",
  "P05 Shortfall to Cost": "Worst 5% Loss Pressure",
  "Expected Loss Per Pack": "Average Loss per Pack",
  "Expected Loss When Losing": "Average Loss When You Miss",
  "Median Loss When Losing": "Typical Loss When You Miss",
  "Tail Value P5": "Bad Pack Floor Value",
  "Typical Pack": "Typical Pack Value",
  "Typical Pack Value": "Typical Pack Value",
  "Bad Pack Floor": "Bad Pack Floor Value",
  "Bad Pack Floor Value": "Bad Pack Floor Value",

  // Stability card
  "Coefficient of Variation": "Outcome Volatility",
  "HHI EV Concentration": "Value Spread",
  "Effective Chase Count": "Cards Carrying Value",
  "Top 1 EV Share": "Top Chase Share",
  "Top 3 EV Share": "Top 3 Share",
  "Top 5 EV Share": "Top 5 Share",
  "Chase Depth": "Cards Carrying Value",
  "Cards Carrying Value": "Cards Carrying Value",
  "Top Card Share": "Top Chase Share",
  "Top Chase Share": "Top Chase Share",
  "Top 3 Share": "Top 3 Share",
  "Top 5 Share": "Top 5 Share",
  "Value Concentration": "Value Spread",
  "Value Spread": "Value Spread",
  "Best Pull": "Best Simulated Pull",
  "Best Simulated Pull": "Best Simulated Pull",

  // Advanced metrics (same mappings if they appear there)
  "Average Loss per Pack": "Average Loss per Pack",
  "Average Loss When You Miss": "Average Loss When You Miss",
  "Coefficient of Variation": "Outcome Volatility",
  "HHI EV Concentration": "Value Concentration",
  "P95 Value / Cost Ratio": "Big Hit Upside",
  "P99 Value / Cost Ratio": "God Pull Upside",
  "Effective Chase Count": "Chase Depth",
};

const METRIC_TOOLTIP_ALIASES = {
  "Chance to Beat Pack Cost": "Probability of Profit",
  "Chance to Miss Pack Cost": "Chance to Miss Pack Cost",
  "Current Pack Cost": "Pack Cost",
  "Pack Market Price": "Pack Cost",
  "Expected Value": "EV / Mean Value",
  "Big Hit Upside": "P95-to-Cost Ratio",
  "God Pull Upside": "P99-to-Cost Ratio",
  "Average Loss per Pack": "Expected Loss Per Pack",
  "Average Loss When You Miss": "Expected Loss When Losing",
  "Typical Loss When You Miss": "Median Loss When Losing",
  "Typical Pack Value": "Typical Pack Value",
  "Bad Pack Floor Value": "Bad Pack Floor Value",
  "Worst 5% Outcome": "Tail Value P5",
  "Chase Depth": "Effective Chase Count",
  "Cards Carrying Value": "Effective Chase Count",
  "Top Card Share": "Top 1 EV Share",
  "Top Chase Share": "Top 1 EV Share",
  "Top 3 Share": "Top 3 EV Share",
  "Top 5 Share": "Top 5 EV Share",
  "Value Concentration": "HHI EV Concentration",
  "EV Concentration": "HHI EV Concentration",
  "Value Spread": "HHI EV Concentration",
  "Best Simulated Pull": "Best Simulated Pull",
  "Average Loss": "Average Loss",
  "Chance at a Big Pull": "Chance at a Big Pull",
};

function buildMetricTooltip({ meaning, impact, direction, interpretation }) {
  return (
    <div className="space-y-1.5 text-left">
      <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
        <li className="flex gap-2">
          <span className="flex-none">•</span>
          <span>
            <span className="font-semibold text-[var(--text-primary)]">Meaning:</span> {meaning}
          </span>
        </li>
        <li className="flex gap-2">
          <span className="flex-none">•</span>
          <span>
            <span className="font-semibold text-[var(--text-primary)]">Score role:</span> {impact}
          </span>
        </li>
        <li className="flex gap-2">
          <span className="flex-none">•</span>
          <span>
            <span className="font-semibold text-[var(--text-primary)]">Direction:</span> {direction}
          </span>
        </li>
        <li className="flex gap-2">
          <span className="flex-none">•</span>
          <span>
            <span className="font-semibold text-[var(--text-primary)]">Interpretation:</span> {interpretation}
          </span>
        </li>
      </ul>
    </div>
  );
}

const PROFIT_SCORE_TOOLTIP_IMPACTS = {
  prob_profit: "Core profit signal",
  mean_value_to_cost_ratio: "Core profit signal",
  median_value_to_cost_ratio: "Core profit signal",
  p95_value_to_cost_ratio: "Core profit signal",
};

/**
 * Tooltip explanations for metrics.
 * Provides short, plain-English descriptions of what each metric means.
 */
export const METRIC_TOOLTIP_EXPLANATIONS = {
  "Probability of Profit": buildMetricTooltip({
    meaning: "Estimated chance a simulated pack returns at least the current pack market price.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.prob_profit,
    direction: "Higher is better",
    interpretation: "Higher values mean simulated openings beat cost more often. This is not a guarantee for any pack.",
  }),
  "EV / Mean Value": buildMetricTooltip({
    meaning: "Expected Value is the average simulated pack value across many openings using modeled pull rates and current card prices.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.mean_value_to_cost_ratio,
    direction: "Higher is better",
    interpretation: "It is a long-run average, not the typical result of a single pack.",
  }),
  "Median-to-Cost Ratio": buildMetricTooltip({
    meaning: "Typical return is the median simulated pack value divided by the current pack market price.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.median_value_to_cost_ratio,
    direction: "Higher is better",
    interpretation: "It shows the middle simulated outcome, which can differ from Expected Value when rare chase cards pull the average upward.",
  }),
  "P95-to-Cost Ratio": buildMetricTooltip({
    meaning: "Big Hit Upside compares the 95th percentile simulated pack outcome against the current pack market price.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.p95_value_to_cost_ratio,
    direction: "Higher is better.",
    interpretation: "Values above 1.00 mean the P95 outcome beats pack cost. This shows upper-end outcomes, not average profitability.",
  }),
  "P99-to-Cost Ratio": buildMetricTooltip({
    meaning: "God Pull Upside is based on the 99th percentile simulated outcome.",
    impact: "Context signal",
    direction: "Higher is better.",
    interpretation: "It represents rare, extreme results near the top 1% of simulations, not a likely single-pack outcome.",
  }),
  ROI: buildMetricTooltip({
    meaning: "Expected return on investment relative to pack cost.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Useful snapshot of expected gain/loss.",
  }),
  "Pack Cost": buildMetricTooltip({
    meaning: "Pack Market Price is the current estimated market cost to buy one pack of this set.",
    impact: "Context signal",
    direction: "Lower is better",
    interpretation: "It is used as the cost basis for EV, risk, and upside comparisons. It is an estimate, not a guaranteed sale or purchase price.",
  }),
  "Average Loss": buildMetricTooltip({
    meaning: "Simple gap between Expected Value and pack cost, shown as a loss when EV is below cost.",
    impact: "Context signal",
    direction: "Closer to zero is better",
    interpretation: "Useful collector-facing shorthand for how far the average pack sits below cost.",
  }),
  "Average Pack Value": buildMetricTooltip({
    meaning: "Expected Value is the average simulated value of one pack using current price inputs and pull-rate assumptions.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "This is a long-run statistical average from simulations, not a guarantee or typical single-pack outcome.",
  }),
  "Chance at a Big Pull": buildMetricTooltip({
    meaning: "Estimated chance a simulated pack clears the page's big-hit threshold.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Shows how often the set lands one of its higher-end outcomes.",
  }),
  "Chance to Miss Pack Cost": buildMetricTooltip({
    meaning: "Estimated chance a simulated pack finishes below the current pack market price.",
    impact: "Safety context",
    direction: "Lower is better",
    interpretation: "This is the inverse of Chance to Beat Pack Cost. It describes simulated frequency, not a guarantee for any pack.",
  }),

  "Expected Loss When Losing / Cost": buildMetricTooltip({
    meaning: "Average loss on losing packs as a fraction of pack cost.",
    impact: "Core safety signal",
    direction: "Lower is better",
    interpretation: "Lower values indicate smaller losses when outcomes are negative.",
  }),
  "Median Loss When Losing / Cost": buildMetricTooltip({
    meaning: "Median loss on losing packs as a fraction of pack cost.",
    impact: "Core safety signal",
    direction: "Lower is better",
    interpretation: "Represents the typical downside severity when a pack loses.",
  }),
  "P05 Shortfall to Cost": buildMetricTooltip({
    meaning: "Worst 5% shortfall relative to pack cost.",
    impact: "Core safety signal",
    direction: "Lower is better",
    interpretation: "Lower values mean less severe downside in the left tail.",
  }),
  "Median Loss When Losing": buildMetricTooltip({
    meaning: "Typical dollar loss amount when a pack outcome is negative.",
    impact: "Core safety signal",
    direction: "Lower is better",
    interpretation: "Shows the typical downside amount on losing outcomes.",
  }),
  "Expected Loss Per Pack": buildMetricTooltip({
    meaning: "Average loss across all simulated packs, including winners and losers.",
    impact: "Context signal",
    direction: "Closer to zero is better",
    interpretation: "Useful downside context, but not a direct runtime V2 Safety score input.",
  }),
  "Expected Loss When Losing": buildMetricTooltip({
    meaning: "Among simulated packs that do not beat the estimated pack market price, this is the average amount lost versus the pack cost.",
    impact: "Core safety signal",
    direction: "Lower is better",
    interpretation: "Shows how painful misses are on average when a pack does not clear cost.",
  }),
  "Tail Value P5": buildMetricTooltip({
    meaning: "Worst 5% Outcome represents the 5th percentile simulated result.",
    impact: "Core safety signal",
    direction: "Higher is better",
    interpretation: "About 5% of simulated openings finish at or below this value.",
  }),
  "Typical Pack Value": buildMetricTooltip({
    meaning: "Typical Pack Value represents the median simulated pack outcome.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "About half of simulated packs finish above this value and half finish below it. It can differ from Expected Value because rare chase cards can pull the average upward.",
  }),
  "Bad Pack Floor Value": buildMetricTooltip({
    meaning: "Bad Pack Floor Value uses the low-end simulated outcome represented by the 5th percentile when available.",
    impact: "Core safety signal",
    direction: "Higher is better",
    interpretation: "It describes downside pressure in weaker simulated outcomes, not the worst possible pack.",
  }),

  "Coefficient of Variation": buildMetricTooltip({
    meaning: "Outcome Volatility measures spread in simulated outcomes using coefficient of variation.",
    impact: "Core stability signal",
    direction: "Lower is better",
    interpretation: "Higher volatility means outcomes are more uneven and chase-dependent.",
  }),
  "HHI EV Concentration": buildMetricTooltip({
    meaning: "EV Concentration measures how much of the set's expected value is carried by a small number of cards.",
    impact: "Context signal",
    direction: "Lower is better",
    interpretation: "Higher concentration means the set relies more heavily on top chase cards. Lower values mean value is more spread out.",
  }),
  "Effective Chase Count": buildMetricTooltip({
    meaning: "Chase Depth estimates how many meaningful chase cards contribute to the set's value profile after accounting for concentration.",
    impact: "Direct Stability score input",
    direction: "Higher is better",
    interpretation: "Higher depth means value is spread across more chase cards instead of relying on one or two cards.",
  }),
  "Top 1 EV Share": buildMetricTooltip({
    meaning: "How much the biggest card carries the set by itself.",
    impact: "Support signal",
    direction: "Lower is better",
    interpretation: "Higher concentration signals dependence on one chase card.",
  }),
  "Top 3 EV Share": buildMetricTooltip({
    meaning: "Share of total EV coming from the top three cards.",
    impact: "Support signal",
    direction: "Lower is better",
    interpretation: "Helps gauge concentration beyond only the top card.",
  }),
  "Top 5 EV Share": buildMetricTooltip({
    meaning: "Share of total EV coming from the top five cards.",
    impact: "Support signal",
    direction: "Lower is better",
    interpretation: "Context metric for EV concentration profile.",
  }),
  "Best Simulated Pull": buildMetricTooltip({
    meaning: "Highest simulated pack result observed in the run.",
    impact: "Reference signal",
    direction: "Higher is better",
    interpretation: "Shows the ceiling, not the typical outcome.",
  }),
  "Expected Value vs Cost": buildMetricTooltip({
    meaning: "Expected Value vs Cost is the mean simulated pack value divided by the current pack market price.",
    impact: "Direct Profit score input",
    direction: "Higher is better",
    interpretation: "1.00 means long-run simulated EV matches pack cost. It does not mean a single pack is expected to break even.",
  }),
  "Typical Return vs Cost": buildMetricTooltip({
    meaning: "Typical Return vs Cost is the median simulated pack value divided by the current pack market price.",
    impact: "Direct Profit score input",
    direction: "Higher is better",
    interpretation: "It shows whether the middle simulated outcome is close to cost, not whether the set is profitable on average.",
  }),
  "Big Hit Upside": buildMetricTooltip({
    meaning: "Big Hit Upside compares the 95th percentile simulated pack outcome against the current pack market price.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Values above 1.00 mean the P95 outcome beats pack cost. This is upper-end upside, not average profitability.",
  }),
  "God Pull Upside": buildMetricTooltip({
    meaning: "God Pull Upside is based on the 99th percentile simulated outcome compared with pack cost.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "It represents rare, extreme opening results near the top 1% of simulations, not a likely outcome.",
  }),
  "Outcome Volatility": buildMetricTooltip({
    meaning: "Outcome Volatility measures how much simulated pack results swing between low and high outcomes using coefficient of variation.",
    impact: "Direct Stability score input",
    direction: "Neutral",
    interpretation: "Higher volatility means outcomes are more uneven and chase-dependent; it is not a price prediction.",
  }),
  "Value Spread": buildMetricTooltip({
    meaning: "How evenly value is distributed across meaningful pulls. Lower spread means value is concentrated into fewer cards or outcomes.",
    impact: "Context signal",
    direction: "Lower is better",
    interpretation: "Contextual concentration/spread signal in runtime V2, not a direct Stability input.",
  }),
  "Cards Carrying Value": buildMetricTooltip({
    meaning: "An effective card-count estimate for how many cards meaningfully support the set's value after accounting for concentration.",
    impact: "Direct Stability score input",
    direction: "Higher is better",
    interpretation: "It can be decimal because it is a concentration metric, not a literal card count.",
  }),
};

/**
 * Score card tooltip explanations.
 * Provides detailed context for Pack Score, Profit, Safety, Desirability, Stability.
 */
export const SCORE_CARD_TOOLTIPS = {
  "Pack Score": "Pack Score",
  "Profit": "Profit Score",
  "Safety": "Safety Score",
  "Desirability": "Opening Desirability",
  "Stability": "Stability Score",
};

/**
 * Helper function to get a tier insight or fallback.
 * Safely retrieves pack score insight for a given tier.
 */
export function getPackScoreInsight(tier) {
  if (!tier) return PACK_SCORE_INSIGHTS.null;
  return PACK_SCORE_INSIGHTS[tier] || PACK_SCORE_INSIGHTS.null;
}

/**
 * Helper function to get friendly label for a metric.
 * Returns the friendly label if available, otherwise returns the original label.
 */
export function getFriendlyMetricLabel(label) {
  if (!label) return label;
  return FRIENDLY_METRIC_LABELS[label] || label;
}

/**
 * Helper function to get tooltip explanation for a metric.
 * Returns explanation if available, otherwise null.
 */
export function getMetricTooltip(label) {
  if (!label) return null;
  return METRIC_TOOLTIP_EXPLANATIONS[label] || METRIC_TOOLTIP_EXPLANATIONS[METRIC_TOOLTIP_ALIASES[label]] || null;
}

/**
 * Helper function to get score card tooltip.
 * Returns tooltip if available, otherwise null.
 */
export function getScoreTootip(scoreType) {
  if (!scoreType) return null;
  return SCORE_CARD_TOOLTIPS[scoreType] || null;
}

/**
 * Helper function to get formatted tooltip JSX for score cards.
 * Returns bullet-formatted JSX content for tooltips.
 */
export function getFormattedTooltip(scoreType) {
  if (scoreType === "Pack Score") {
    return (
      <div className="space-y-2 text-left">
        <p className="font-semibold text-[var(--text-primary)]">Rip Score</p>
        <p className="text-[var(--text-secondary)]">Measures overall pack rip quality by combining:</p>
        <ul className="space-y-1.5 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Profit</span>
              <br />
              <span className="text-[11px]">Upside and return potential</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Safety</span>
              <br />
              <span className="text-[11px]">Downside risk and loss severity</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Opening Desirability</span>
              <br />
              <span className="text-[11px]">Collector appeal and chase appeal</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Stability</span>
              <br />
              <span className="text-[11px]">Consistency of outcomes</span>
            </span>
          </li>
        </ul>
        <p className="pt-1 text-[11px] text-[var(--text-secondary)]">RIP Score combines pack value, risk, stability, and Opening Desirability to estimate how appealing a set is to open.</p>
      </div>
    );
  }

  if (scoreType === "Profit") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">Can You Win?</p>
        <p className="text-[var(--text-secondary)]">This shows how often packs beat their cost and how much upside the better pulls create.</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures upside and return potential</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Core component of Rip Score</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers probability of profit</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers Expected Value</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers typical return</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers high-end upside</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers return on investment</span>
          </li>
        </ul>
      </div>
    );
  }

  if (scoreType === "Safety") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">How Bad Are Misses?</p>
        <p className="text-[var(--text-secondary)]">This shows how painful losing packs are compared with other sets.</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures downside protection</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Core component of Rip Score</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers average loss</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers typical loss</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers worst-case/tail outcomes</span>
          </li>
        </ul>
      </div>
    );
  }

  if (scoreType === "Desirability") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">Opening Desirability</p>
        <p className="text-[var(--text-secondary)]">Opening Desirability combines Collector Appeal and Chase Appeal to estimate how compelling the set is to open.</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures intrinsic set appeal</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Core component of Rip Score</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Independent of market price</span>
          </li>
        </ul>
      </div>
    );
  }

  if (scoreType === "Stability") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">How Balanced Is This Set?</p>
        <p className="text-[var(--text-secondary)]">This shows whether value is spread across multiple cards or mostly depends on one chase.</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures outcome consistency</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Core component of Rip Score</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers outcome volatility</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers EV concentration</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers effective chase depth</span>
          </li>
        </ul>
      </div>
    );
  }

  return null;
}
