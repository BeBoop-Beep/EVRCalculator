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
  "Probability of Profit": "Probability of Profit",
  "EV / Mean Value": "Average Return vs Cost",
  "Median-to-Cost Ratio": "Typical Outcome vs Cost",
  "P95-to-Cost Ratio": "High-End Upside vs Cost",
  ROI: "Return on Investment",
  "Pack Cost": "Pack Cost",

  // Safety card
  "Expected Loss When Losing / Cost": "Average Loss vs Cost",
  "Median Loss When Losing / Cost": "Typical Loss vs Cost",
  "P05 Shortfall to Cost": "Worst 5% Loss Pressure",
  "Median Loss When Losing": "Typical Loss Amount",
  "Tail Value P5": "Worst 5% Outcome",

  // Stability card
  "Coefficient of Variation": "Outcome Volatility",
  "HHI EV Concentration": "EV Concentration",
  "Effective Chase Count": "Effective Chase Depth",
  "Top 1 EV Share": "Top Card EV Share",
  "Top 3 EV Share": "Top 3 Cards EV Share",
  "Top 5 EV Share": "Top 5 Cards EV Share",

  // Advanced metrics (same mappings if they appear there)
  "Expected Loss Per Pack": "Expected Loss Per Pack",
  "Expected Loss When Losing": "Expected Loss When Losing",
  "Coefficient of Variation": "Outcome Volatility",
  "HHI EV Concentration": "EV Concentration",
  "P95 Value / Cost Ratio": "P95 Value / Cost Ratio",
  "Effective Chase Count": "Effective Chase Depth",
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
            <span className="font-semibold text-[var(--text-primary)]">Score impact:</span> {impact}
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

// TODO: Keep these tooltip percentages aligned with backend pack_score.weights_pct.profit_score
// until the Explore page consumes the live weights payload directly.
const PROFIT_SCORE_TOOLTIP_IMPACTS = {
  prob_profit: "Direct (27.5% of Profit Score)",
  mean_value_to_cost_ratio: "Direct (25% of Profit Score)",
  median_value_to_cost_ratio: "Direct (20% of Profit Score)",
  p95_value_to_cost_ratio: "Direct (27.5% of Profit Score)",
};

/**
 * Tooltip explanations for metrics.
 * Provides short, plain-English descriptions of what each metric means.
 */
export const METRIC_TOOLTIP_EXPLANATIONS = {
  "Probability of Profit": buildMetricTooltip({
    meaning: "Estimated chance a simulated pack returns at least pack cost.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.prob_profit,
    direction: "Higher is better",
    interpretation: "Higher values mean profit outcomes occur more frequently.",
  }),
  "EV / Mean Value": buildMetricTooltip({
    meaning: "Average simulated return divided by pack cost.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.mean_value_to_cost_ratio,
    direction: "Higher is better",
    interpretation: "Values above 1.00 indicate average return exceeds cost.",
  }),
  "Median-to-Cost Ratio": buildMetricTooltip({
    meaning: "Typical (median) simulated return divided by pack cost.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.median_value_to_cost_ratio,
    direction: "Higher is better",
    interpretation: "Shows whether the middle outcome usually beats cost.",
  }),
  "P95-to-Cost Ratio": buildMetricTooltip({
    meaning: "95th percentile simulated pack outcome divided by pack cost.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.p95_value_to_cost_ratio,
    direction: "Higher is better",
    interpretation: "Captures realistic high-end chase upside in strong outcome tails.",
  }),
  ROI: buildMetricTooltip({
    meaning: "Expected return on investment relative to pack cost.",
    impact: "Context only",
    direction: "Higher is better",
    interpretation: "Useful snapshot of expected gain/loss, but not directly scored.",
  }),
  "Pack Cost": buildMetricTooltip({
    meaning: "Estimated market cost to open one pack.",
    impact: "Context only",
    direction: "Lower is better",
    interpretation: "Used as a denominator for ratios, not scored directly.",
  }),

  "Expected Loss When Losing / Cost": buildMetricTooltip({
    meaning: "Average loss on losing packs as a fraction of pack cost.",
    impact: "Direct (34% of Safety Score)",
    direction: "Lower is better",
    interpretation: "Lower values indicate smaller losses when outcomes are negative.",
  }),
  "Median Loss When Losing / Cost": buildMetricTooltip({
    meaning: "Median loss on losing packs as a fraction of pack cost.",
    impact: "Direct (33% of Safety Score)",
    direction: "Lower is better",
    interpretation: "Represents the typical downside severity when a pack loses.",
  }),
  "P05 Shortfall to Cost": buildMetricTooltip({
    meaning: "Worst 5% shortfall relative to pack cost.",
    impact: "Direct (33% of Safety Score)",
    direction: "Lower is better",
    interpretation: "Lower values mean less severe downside in the left tail.",
  }),
  "Median Loss When Losing": buildMetricTooltip({
    meaning: "Typical dollar loss amount when a pack outcome is negative.",
    impact: "Context only",
    direction: "Lower is better",
    interpretation: "Displayed for readability; ratio metrics drive Safety scoring.",
  }),
  "Tail Value P5": buildMetricTooltip({
    meaning: "Dollar value at the 5th percentile of simulated outcomes.",
    impact: "Context only",
    direction: "Higher is better",
    interpretation: "Shows tail outcome level, while shortfall ratio drives scoring.",
  }),

  "Coefficient of Variation": buildMetricTooltip({
    meaning: "Outcome dispersion relative to mean return.",
    impact: "Direct (65% of Stability Score)",
    direction: "Lower is better",
    interpretation: "Lower volatility implies more consistent expected outcomes.",
  }),
  "HHI EV Concentration": buildMetricTooltip({
    meaning: "Concentration index of EV shares across cards.",
    impact: "Indirect",
    direction: "Lower is better",
    interpretation: "Higher concentration reduces effective chase depth used in scoring.",
  }),
  "Effective Chase Count": buildMetricTooltip({
    meaning: "Effective number of meaningful EV contributors (1/HHI).",
    impact: "Direct (35% of Stability Score)",
    direction: "Higher is better",
    interpretation: "Higher values indicate value is spread across more cards.",
  }),
  "Top 1 EV Share": buildMetricTooltip({
    meaning: "Share of total EV coming from the single top card.",
    impact: "Context only",
    direction: "Lower is better",
    interpretation: "Higher concentration signals dependence on one chase card.",
  }),
  "Top 3 EV Share": buildMetricTooltip({
    meaning: "Share of total EV coming from the top three cards.",
    impact: "Context only",
    direction: "Lower is better",
    interpretation: "Helps gauge concentration beyond only the top card.",
  }),
  "Top 5 EV Share": buildMetricTooltip({
    meaning: "Share of total EV coming from the top five cards.",
    impact: "Context only",
    direction: "Lower is better",
    interpretation: "Context metric for EV concentration profile.",
  }),
};

/**
 * Score card tooltip explanations.
 * Provides detailed context for Pack Score, Profit, Safety, Stability.
 */
export const SCORE_CARD_TOOLTIPS = {
  "Pack Score": "Pack Score",
  "Profit": "Profit Score",
  "Safety": "Safety Score",
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
  return METRIC_TOOLTIP_EXPLANATIONS[label] || null;
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
        <p className="font-semibold text-[var(--text-primary)]">Pack Score (PACK)</p>
        <p className="text-[var(--text-secondary)]">Measures overall pack rip quality by combining:</p>
        <ul className="space-y-1.5 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Profit (45%)</span>
              <br />
              <span className="text-[11px]">Upside and return potential</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Safety (30%)</span>
              <br />
              <span className="text-[11px]">Downside risk and loss severity</span>
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Stability (25%)</span>
              <br />
              <span className="text-[11px]">Consistency of outcomes</span>
            </span>
          </li>
        </ul>
        <p className="pt-1 text-[11px] text-[var(--text-secondary)]">Higher scores indicate a stronger overall rip profile based on expected value, risk, and consistency.</p>
      </div>
    );
  }

  if (scoreType === "Profit") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">Profit Score</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures upside and return potential</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Weight: 45%</span> of Pack Score
            </span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers probability of profit</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Considers average return</span>
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
        <p className="font-semibold text-[var(--text-primary)]">Safety Score</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures downside protection</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Weight: 30%</span> of Pack Score
            </span>
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

  if (scoreType === "Stability") {
    return (
      <div className="space-y-1.5 text-left">
        <p className="font-semibold text-[var(--text-primary)]">Stability Score</p>
        <ul className="space-y-1 pl-3 text-[var(--text-secondary)]">
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>Measures outcome consistency</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-none">•</span>
            <span>
              <span className="font-semibold text-[var(--text-primary)]">Weight: 25%</span> of Pack Score
            </span>
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
