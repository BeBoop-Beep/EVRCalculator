"use client";

import { useMemo } from "react";
import MultiSelectFilter from "@/components/ui/MultiSelectFilter";
import RankingsSearchInput from "./RankingsSearchInput";

function latestOnly(current, next) {
  if (!next.length) return "";
  return next.find((id) => id !== current) || next[next.length - 1];
}

export default function CardRankingsFilterBar({ filters, facets, onChange, onClear }) {
  const eraOptions = useMemo(() => (facets?.eras || []).map((era) => ({
    id: String(era.eraId), label: era.eraName,
  })), [facets]);
  const setOptions = useMemo(() => (facets?.sets || [])
    .filter((set) => !filters.era || String(set.eraId) === filters.era)
    .map((set) => ({ id: String(set.setId), label: set.setName })), [facets, filters.era]);
  const rarityOptions = useMemo(() => (facets?.rarities || []).map((rarity) => ({
    id: String(rarity.key), label: rarity.name,
  })), [facets]);
  const hasFilters = Boolean(filters.search || filters.era || filters.set || filters.rarity);
  const single = (key) => (next) => onChange(key, latestOnly(filters[key], next));

  return (
    <div data-card-ranking-filters className="grid gap-3 border-b border-[var(--border-subtle)] p-3 sm:grid-cols-2 desk:grid-cols-4">
      <div className="self-end">
        <RankingsSearchInput value={filters.search} onChange={(event) => onChange("search", event.target.value)} entity="Cards" />
      </div>
      <MultiSelectFilter label="Era" name="card-era" options={eraOptions} selectedIds={filters.era ? [filters.era] : []} onChange={single("era")} allLabel="All Eras" summaryNoun="Eras" searchable searchPlaceholder="Search Eras…" showChips />
      <MultiSelectFilter label="Set" name="card-set" options={setOptions} selectedIds={filters.set ? [filters.set] : []} onChange={single("set")} allLabel="All Sets" summaryNoun="Sets" searchable searchPlaceholder="Search Sets…" showChips />
      <MultiSelectFilter label="Rarity" name="card-rarity" options={rarityOptions} selectedIds={filters.rarity ? [filters.rarity] : []} onChange={single("rarity")} allLabel="All Rarities" summaryNoun="Rarities" searchable searchPlaceholder="Search Rarities…" showChips />
      <div className="desk:col-span-4 flex justify-end">
        <button type="button" disabled={!hasFilters} onClick={onClear} className="rounded-lg px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--accent)] disabled:opacity-40">Clear filters</button>
      </div>
    </div>
  );
}
