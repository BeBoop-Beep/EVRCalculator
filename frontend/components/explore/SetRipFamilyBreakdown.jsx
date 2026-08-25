"use client";

import React from "react";
import { RANK_CONFIG, topPercentToTier } from "../../constants/rankConfig.mjs";
import { formatPublicRipScore } from "../../constants/exploreRankingConfig.mjs";

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

export function displayFamilyScores(setRip) {
  const source = Array.isArray(setRip?.displayFamilyScores) ? setRip.displayFamilyScores : setRip?.familyScores;
  return Array.isArray(source)
    ? source.filter((entry) => entry && Number.isFinite(Number(entry.score)) && Number(entry.rank) > 0 && Number(entry.cohortSize) > 0)
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
      <span className="text-right text-sm font-semibold tabular-nums text-[var(--text-primary)]">{formatPublicRipScore(entry.score)} / 10</span>
      <span className="text-right text-xs font-semibold tabular-nums text-[var(--text-primary)]">#{entry.rank}</span>
      <FamilyTierBadge tier={tier} />
      {!compact && showTakeaway ? <span className="text-xs text-[var(--text-secondary)]">{takeaway}</span> : null}
    </div>
  );
}

export function FamilySnapshot({ setRip, compact = false, layout = "rows" }) {
  const families = displayFamilyScores(setRip);
  if (!families.length) return <span className="text-xs text-[var(--text-secondary)]">Family scores unavailable</span>;
  if (layout === "modules") {
    const wideColumnCount = Math.min(families.length, 7);
    return (
      <div
        data-family-snapshot
        data-wide-family-columns={wideColumnCount}
        className={`set-rip-family-snapshot ${compact ? "set-rip-family-snapshot--compact" : "set-rip-family-snapshot--wide"}`}
        style={{ "--family-columns": wideColumnCount }}
      >
        {families.map((entry) => {
          const tier = familyTier(entry);
          const tierColor = tier ? RANK_CONFIG[tier]?.color : null;
          return <div data-family-module key={entry.family} className="set-rip-family-column"><span className="line-clamp-2 min-h-[1.4rem] text-[10px] font-semibold leading-[1.1] text-[var(--text-secondary)]">{snapshotFamilyLabel(entry.family)}</span><strong className="text-[15px] font-bold leading-none tabular-nums text-[var(--text-primary)]">{formatPublicRipScore(entry.score)}</strong><span className="whitespace-nowrap text-[10px] leading-none text-[var(--text-secondary)]">#{entry.rank} <span aria-hidden="true">·</span> <span style={tierColor ? { color: tierColor } : undefined}>{tier || "—"}</span></span></div>;
        })}
      </div>
    );
  }
  return <div className="divide-y divide-[var(--border-subtle)]">{families.map((entry) => <FamilyScoreRow key={entry.family} entry={entry} compact={compact} />)}</div>;
}

export const RANKINGS_FAMILY_COLUMNS = Object.freeze([
  { key: "loose", label: "Loose Pack", fullLabel: "Loose Booster Pack", families: ["loose_booster_pack"] },
  { key: "sleeved", label: "Sleeved Pack", fullLabel: "Sleeved Booster Pack", families: ["sleeved_booster_pack"] },
  { key: "bundle", label: "Bundle", fullLabel: "Booster Bundle", families: ["booster_bundle"] },
  { key: "etb", label: "ETB", fullLabel: "Elite Trainer Box", families: ["elite_trainer_box"] },
  { key: "pc-etb", label: "PC ETB", fullLabel: "Pokémon Center Elite Trainer Box", info: "Pokémon Center Elite Trainer Box — an Elite Trainer Box edition sold through Pokémon Center, often with exclusive packaging or promo treatment depending on the release.", families: ["pokemon_center_elite_trainer_box"] },
  { key: "half-box", label: "Half Box", fullLabel: "Half Booster Box", info: "Half Booster Box — a smaller sealed booster-box format containing about half the booster packs of the standard Booster Box for that release.", families: ["half_booster_box"] },
  { key: "booster-box", label: "Booster Box", fullLabel: "Booster Box", families: ["booster_box"] },
  { key: "enhanced-box", label: "Enhanced Box", fullLabel: "Enhanced Booster Box", families: ["enhanced_booster_box"] },
]);

function FixedFamilyResult({ entry, identifier = null }) {
  const tier = familyTier(entry);
  const tierColor = tier ? RANK_CONFIG[tier]?.color : null;
  return (
    <span data-fixed-family-result={entry.family} className="flex flex-col items-center gap-1 text-center">
      {identifier ? <span className="text-[9px] font-bold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{identifier}</span> : null}
      <strong className="text-sm font-bold leading-none tabular-nums text-[var(--text-primary)]">{formatPublicRipScore(entry.score)}</strong>
      <span className="whitespace-nowrap text-[10px] leading-none text-[var(--text-secondary)]">#{entry.rank} <span aria-hidden="true">·</span> <span style={tierColor ? { color: tierColor } : undefined}>{tier || "—"}</span></span>
    </span>
  );
}

export function RankingsFamilyCells({ setRip }) {
  const familyByKey = new Map(displayFamilyScores(setRip).map((entry) => [entry.family, entry]));
  return RANKINGS_FAMILY_COLUMNS.map((column) => {
    const entries = column.families.map((family) => familyByKey.get(family)).filter(Boolean);
    return (
      <td key={column.key} data-rankings-family-column={column.key} className="px-1.5 text-center align-middle">
        {entries.length ? (
          <span className="flex flex-col items-center gap-2">
            {entries.map((entry) => <FixedFamilyResult key={entry.family} entry={entry} identifier={column.key === "special" ? (entry.family === "special_collection" ? "SPC" : "UPC") : null} />)}
          </span>
        ) : <span className="text-xs text-[var(--text-secondary)]">—</span>}
      </td>
    );
  });
}

export function whySetRanks(setRip) {
  const families = participatingFamilyScores(setRip);
  if (!families.length) return "Product-family evidence is not available yet.";
  const strong = families.filter((entry) => ["S", "A"].includes(familyTier(entry))).length;
  if (strong === families.length) return "Elite performance across nearly every opening format.";
  if (strong >= Math.ceil(families.length / 2)) return "Strong results across most participating product families.";
  return "Standout strength in its best participating product families.";
}
