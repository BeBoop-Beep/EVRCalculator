"use client";

import { topPercentToTier } from "../../constants/rankConfig.mjs";

const FAMILY_LABELS = Object.freeze({
  loose_booster_pack: "Booster Pack",
  sleeved_booster_pack: "Sleeved Pack",
  booster_box: "Booster Box",
  half_booster_box: "Half Booster Box",
  enhanced_booster_box: "Enhanced Booster Box",
  booster_bundle: "Booster Bundle",
  elite_trainer_box: "ETB",
  special_collection: "SPC",
  ultra_premium_collection: "UPC",
  three_pack_blister: "3-Pack Blister",
});

export function familyLabel(family) {
  return FAMILY_LABELS[family] || String(family || "Product family")
    .split("_").filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

export function familyTier(entry) {
  const rank = Number(entry?.rank);
  const cohortSize = Number(entry?.cohortSize);
  return Number.isFinite(rank) && cohortSize > 0
    ? topPercentToTier((rank / cohortSize) * 100)
    : null;
}

export function setRipTier(setRip) {
  const rank = Number(setRip?.rank);
  const cohortSize = Number(setRip?.cohortSize);
  return Number.isFinite(rank) && cohortSize > 0
    ? topPercentToTier((rank / cohortSize) * 100)
    : null;
}

export function participatingFamilyScores(setRip) {
  return Array.isArray(setRip?.familyScores)
    ? setRip.familyScores.filter((entry) => entry && Number.isFinite(Number(entry.score)) && Number(entry.rank) > 0 && Number(entry.cohortSize) > 0)
    : [];
}

export function familyEvidenceScores(setRip) {
  return Array.isArray(setRip?.familyScores)
    ? setRip.familyScores.filter((entry) => entry && typeof entry.family === "string" && entry.family.trim())
    : [];
}

export function participatingFamilyCount(setRip) {
  const canonicalCount = Number(setRip?.participatingFamilyCount);
  return Number.isInteger(canonicalCount) && canonicalCount >= 0
    ? canonicalCount
    : familyEvidenceScores(setRip).length;
}

export function isEnrichedSetRipContract(setRip) {
  const families = participatingFamilyScores(setRip);
  return Number.isFinite(Number(setRip?.score))
    && Number.isInteger(Number(setRip?.rank))
    && Number(setRip.rank) > 0
    && Number.isInteger(Number(setRip?.cohortSize))
    && Number(setRip.cohortSize) > 0
    && families.length > 0;
}

export function selectPreferredSetRipContract(...candidates) {
  return candidates.find(isEnrichedSetRipContract)
    || candidates.find((candidate) => candidate && typeof candidate === "object")
    || null;
}

export function FamilyPlaceholder({ family }) {
  const label = familyLabel(family);
  return <span aria-hidden="true" data-family-media-slot className="inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] text-[9px] font-bold uppercase text-[var(--text-secondary)]">{label.slice(0, 3)}</span>;
}

export function FamilyTierBadge({ tier }) {
  return tier ? <span className="inline-flex whitespace-nowrap rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-primary)]">{tier} Tier</span> : null;
}

export function FamilyScoreRow({ entry, compact = false, showTakeaway = false }) {
  const tier = familyTier(entry);
  const takeaway = entry.rank === 1
    ? "Leads its eligible set-family cohort."
    : `Ranks #${entry.rank} among ${entry.cohortSize} eligible sets.`;
  return (
    <div data-family-score-row className={`grid min-w-0 items-center gap-2 ${compact ? "grid-cols-[2rem_minmax(0,1fr)_auto_auto] py-2" : "grid-cols-[2rem_minmax(0,1fr)_4.5rem_4rem_4.5rem_minmax(9rem,1fr)] py-3"}`}>
      <FamilyPlaceholder family={entry.family} />
      <span className="min-w-0 truncate text-xs font-semibold text-[var(--text-primary)]">{familyLabel(entry.family)}</span>
      <span className="text-right text-sm font-semibold tabular-nums text-[var(--text-primary)]">{Number(entry.score).toFixed(1)}</span>
      <span className="text-right text-xs font-semibold tabular-nums text-[var(--text-primary)]">#{entry.rank}</span>
      <FamilyTierBadge tier={tier} />
      {!compact && showTakeaway ? <span className="text-xs text-[var(--text-secondary)]">{takeaway}</span> : null}
    </div>
  );
}

export function FamilySnapshot({ setRip, compact = false, layout = "rows" }) {
  const families = participatingFamilyScores(setRip);
  if (!families.length) return <span className="text-xs text-[var(--text-secondary)]">Family scores unavailable</span>;
  if (layout === "modules") {
    return (
      <div className="flex flex-wrap gap-1.5">
        {families.map((entry) => {
          const tier = familyTier(entry);
          return <div key={entry.family} className="grid min-w-[7.5rem] grid-cols-[1.6rem_minmax(0,1fr)] items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-2 py-1.5"><FamilyPlaceholder family={entry.family} /><span className="min-w-0"><span className="block truncate text-[9px] font-bold uppercase text-[var(--text-secondary)]">{familyLabel(entry.family)}</span><span className="mt-0.5 flex items-baseline justify-between gap-2"><strong className="text-xs tabular-nums text-[var(--text-primary)]">{Number(entry.score).toFixed(1)}</strong><span className="whitespace-nowrap text-[9px] text-[var(--text-secondary)]">#{entry.rank} · {tier || "—"}</span></span></span></div>;
        })}
      </div>
    );
  }
  return <div className="divide-y divide-[var(--border-subtle)]">{families.map((entry) => <FamilyScoreRow key={entry.family} entry={entry} compact={compact} />)}</div>;
}

export function whySetRanks(setRip) {
  const families = participatingFamilyScores(setRip);
  if (!families.length) return "Product-family evidence is not available yet.";
  const strong = families.filter((entry) => ["S", "A"].includes(familyTier(entry))).length;
  if (strong === families.length) return "Elite performance across nearly every opening format.";
  if (strong >= Math.ceil(families.length / 2)) return "Strong results across most participating product families.";
  return "Its strongest product families lift the combined Set RIP result.";
}
