"use client";

import React from "react";
import { topPercentToTier } from "../../constants/rankConfig.mjs";

const FAMILY_LABELS = Object.freeze({
  loose_booster_pack: "Booster Pack",
  sleeved_booster_pack: "Sleeved Pack",
  booster_box: "Booster Box",
  half_booster_box: "Half Booster Box",
  enhanced_booster_box: "Enhanced Booster Box",
  booster_bundle: "Booster Bundle",
  elite_trainer_box: "ETB",
  pokemon_center_elite_trainer_box: "Pokémon Center Elite Trainer Box",
  special_collection: "SPC",
  ultra_premium_collection: "UPC",
  three_pack_blister: "3-Pack Blister",
});

export function familyLabel(family) {
  return FAMILY_LABELS[family] || String(family || "Product family")
    .split("_").filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

function snapshotFamilyLabel(family) {
  if (family === "pokemon_center_elite_trainer_box") return "Pokémon Center ETB";
  return familyLabel(family);
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

export function FamilyTierBadge({ tier }) {
  return tier ? <span className="inline-flex whitespace-nowrap rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-primary)]">{tier} Tier</span> : null;
}

export function FamilyScoreRow({ entry, compact = false, showTakeaway = false }) {
  const tier = familyTier(entry);
  const takeaway = entry.rank === 1
    ? "Leads its eligible set-family cohort."
    : `Ranks #${entry.rank} among ${entry.cohortSize} eligible sets.`;
  return (
    <div data-family-score-row className={`grid min-w-0 items-center gap-3 ${compact ? "grid-cols-[minmax(0,1fr)_3.75rem_2.5rem_auto] py-2.5" : "grid-cols-[minmax(13rem,1.35fr)_4.5rem_4rem_4.75rem_minmax(11rem,1fr)] py-3.5"}`}>
      <span className="min-w-0 text-xs font-semibold leading-snug text-[var(--text-primary)]">{familyLabel(entry.family)}</span>
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
      <div data-family-snapshot className={`grid rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-1 ${compact ? "grid-cols-2" : "grid-cols-3 xl:grid-cols-5"}`}>
        {families.map((entry) => {
          const tier = familyTier(entry);
          return <div data-family-module key={entry.family} className="flex min-w-0 flex-col justify-between border-b border-r border-[var(--border-subtle)]/60 px-1.5 py-0.5 last:border-r-0"><span className="min-h-[1.125rem] text-[8px] font-bold uppercase leading-[1.1] text-[var(--text-secondary)]">{snapshotFamilyLabel(entry.family)}</span><strong className="text-xs leading-none tabular-nums text-[var(--text-primary)]">{Number(entry.score).toFixed(1)}</strong><span className="whitespace-nowrap text-[9px] leading-none text-[var(--text-secondary)]">#{entry.rank} · {tier || "—"}</span></div>;
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
