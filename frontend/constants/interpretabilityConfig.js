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
  "EV / Mean Value": "Average Return vs Cost",
  "Median-to-Cost Ratio": "Typical Outcome vs Cost",
  "P95-to-Cost Ratio": "Big Hit Upside",
  "P95 Value / Cost Ratio": "Big Hit Upside",
  ROI: "Return on Investment",
  "Pack Cost": "Estimated Pack Market Price",
  "Average Pack Value": "Average Pack Value",
  "Current Pack Cost": "Estimated Pack Market Price",
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
  "Effective Chase Count": "Chase Depth",
};

const METRIC_TOOLTIP_ALIASES = {
  "Chance to Beat Pack Cost": "Probability of Profit",
  "Current Pack Cost": "Pack Cost",
  "Big Hit Upside": "P95-to-Cost Ratio",
  "Average Loss per Pack": "Expected Loss Per Pack",
  "Average Loss When You Miss": "Expected Loss When Losing",
  "Typical Loss When You Miss": "Median Loss When Losing",
  "Typical Pack Value": "Typical Pack Value",
  "Bad Pack Floor Value": "Bad Pack Floor Value",
  "Chase Depth": "Effective Chase Count",
  "Cards Carrying Value": "Effective Chase Count",
  "Top Card Share": "Top 1 EV Share",
  "Top Chase Share": "Top 1 EV Share",
  "Top 3 Share": "Top 3 EV Share",
  "Top 5 Share": "Top 5 EV Share",
  "Value Concentration": "HHI EV Concentration",
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
    meaning: "Shows the stronger upside outcomes when a pack lands in its better results.",
    impact: PROFIT_SCORE_TOOLTIP_IMPACTS.p95_value_to_cost_ratio,
    direction: "Higher is better.",
    interpretation: "Higher values mean the set has stronger high-end payoff relative to pack cost.",
  }),
  ROI: buildMetricTooltip({
    meaning: "Expected return on investment relative to pack cost.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Useful snapshot of expected gain/loss.",
  }),
  "Pack Cost": buildMetricTooltip({
    meaning: "Estimated market snapshot for this pack. Prices may be incomplete, delayed, noisy, or change quickly. This is used as an input to the simulation, not a guaranteed sale or purchase price.",
    impact: "Context signal",
    direction: "Lower is better",
    interpretation: "Used as a denominator for ratio metrics.",
  }),
  "Average Loss": buildMetricTooltip({
    meaning: "Simple gap between average pack value and pack cost, shown as a loss when average value is below cost.",
    impact: "Context signal",
    direction: "Closer to zero is better",
    interpretation: "Useful collector-facing shorthand for how far the average pack sits below cost.",
  }),
  "Average Pack Value": buildMetricTooltip({
    meaning: "The average simulated value of one pack using current price inputs and pull-rate assumptions. Real openings can be much higher or much lower.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "This is a statistical average from simulations, not a guarantee or typical outcome.",
  }),
  "Chance at a Big Pull": buildMetricTooltip({
    meaning: "Estimated chance a simulated pack clears the page's big-hit threshold.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Shows how often the set lands one of its higher-end outcomes.",
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
    impact: "Core safety signal",
    direction: "Closer to zero is better",
    interpretation: "This is the unconditional downside drag per pack.",
  }),
  "Tail Value P5": buildMetricTooltip({
    meaning: "Dollar value at the 5th percentile of simulated outcomes.",
    impact: "Core safety signal",
    direction: "Higher is better",
    interpretation: "Shows the low-end outcome level in weaker runs.",
  }),
  "Typical Pack Value": buildMetricTooltip({
    meaning: "The middle simulated pack result. Half the packs did better, half did worse.",
    impact: "Context signal",
    direction: "Higher is better",
    interpretation: "Useful shorthand for what a normal rip looks like.",
  }),
  "Bad Pack Floor Value": buildMetricTooltip({
    meaning: "A low-end pack result from the worse side of simulations.",
    impact: "Core safety signal",
    direction: "Higher is better",
    interpretation: "Shows how ugly bad runs can get near the left tail.",
  }),

  "Coefficient of Variation": buildMetricTooltip({
    meaning: "Outcome dispersion relative to mean return.",
    impact: "Core stability signal",
    direction: "Lower is better",
    interpretation: "Lower volatility implies more consistent expected outcomes.",
  }),
  "HHI EV Concentration": buildMetricTooltip({
    meaning: "Lower concentration means value is spread across more cards.",
    impact: "Core stability signal",
    direction: "Lower is better",
    interpretation: "Higher concentration reduces effective chase depth used in scoring.",
  }),
  "Effective Chase Count": buildMetricTooltip({
    meaning: "Higher means more cards meaningfully help the set's value.",
    impact: "Core stability signal",
    direction: "Higher is better",
    interpretation: "Higher values indicate value is spread across more cards.",
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
              <span className="font-semibold text-[var(--text-primary)]">Stability</span>
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
