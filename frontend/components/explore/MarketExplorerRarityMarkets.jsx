"use client";
import React, { useMemo, useState } from "react";
import { normalizeQuerySpec, QUERY_ASSET_CARDS } from "../../lib/explore/marketExplorerQuery.mjs";
import { ASSET_OPTION_ACTION, normalizeRarityOptions } from "../../lib/explore/marketExplorerAssetOptions.mjs";
import MarketExplorerAssetMarketSelector from "./MarketExplorerAssetMarketSelector";

const clean = (value) => String(value || "").trim().toLowerCase();
const isSingleRarityQuery = (series, id) => { const spec = series?.spec; return spec?.asset === QUERY_ASSET_CARDS && spec?.mode === "all" && (spec?.segmentIds || []).length === 1 && spec.segmentIds[0] === id && !(spec?.eraIds || []).length && !(spec?.setIds || []).length && !(spec?.pokemonIds || []).length && !(spec?.priceSegmentIds || []).length && !(spec?.releaseAgeCohortIds || []).length; };

export default function MarketExplorerRarityMarkets({ directory = [], rarityOptions = [], assetOptions = null, activeKeys = [], pendingKeys = [], activeSeries = [], canCompare = false, onSelect, onAddQuery, onAddCanonicalRarity, onRemoveQuery, disclosureOpen, onDisclosureChange }) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [pendingId, setPendingId] = useState(null);
  const [message, setMessage] = useState("");
  const preparedBySegment = useMemo(() => new Map(directory.filter((m) => m?.market_type === "prepared_rarity" && m?.metadata?.segmentId).map((m) => [String(m.metadata.segmentId), m])), [directory]);
  const preparedByLabel = useMemo(() => new Map(directory.filter((m) => m?.market_type === "prepared_rarity").map((m) => [clean(m.label), m])), [directory]);
  const v2Options = useMemo(() => normalizeRarityOptions(assetOptions), [assetOptions]);
  const options = useMemo(() => { if (v2Options.length) return v2Options; const canonical = rarityOptions.map((entry) => ({ id: String(entry.key || entry.id || ""), label: String(entry.label || entry.name || entry.key || entry.id || "") })).filter((entry) => entry.id && entry.label); if (canonical.length) return canonical; return directory.filter((m) => m?.market_type === "prepared_rarity").map((m) => ({ id: String(m?.metadata?.segmentId || m.market_key), label: m.label })); }, [directory, rarityOptions, v2Options]);
  const stateFor = (option) => { const prepared = option.action === ASSET_OPTION_ACTION.prepared ? { market_key: option.marketKey } : preparedBySegment.get(option.id) || preparedByLabel.get(clean(option.label)) || null; const query = option.action === ASSET_OPTION_ACTION.build || !prepared ? activeSeries.find((series) => isSingleRarityQuery(series, option.id)) || null : null; return { prepared, query, active: Boolean((prepared && activeKeys.includes(prepared.market_key)) || query) }; };
  const presented = options.filter((option) => !clean(search) || clean(option.label).includes(clean(search))).map((option) => { const state = stateFor(option); return { ...option, active: state.active, pending: pendingId === option.id || Boolean(state.prepared && pendingKeys.includes(state.prepared.market_key)), unavailable: option.action === ASSET_OPTION_ACTION.none, reason: option.action === ASSET_OPTION_ACTION.none ? option.reason : null, interaction: state }; });
  const activeCount = options.filter((option) => stateFor(option).active).length;
  const toggle = async (option) => { const state = option.interaction || stateFor(option); setMessage(""); if (option.unavailable) return; if (state.prepared) { onSelect?.(state.prepared.market_key); return; } if (state.query) { onRemoveQuery?.(state.query.key); return; } setPendingId(option.id); try { const spec = normalizeQuerySpec({ asset: QUERY_ASSET_CARDS, segmentIds: [option.id], mode: "all" }); const add = canCompare ? onAddQuery : (onAddCanonicalRarity || onAddQuery); const outcome = await add?.(spec); if (outcome === "duplicate") setMessage("That rarity market is already active."); } catch (error) { setMessage(error?.message || "Unable to add this rarity market."); } finally { setPendingId(null); } };
  if (!options.length) return null;
  return <MarketExplorerAssetMarketSelector disclosureId="rarities" heading="Rarity Markets" summary={activeCount ? `${activeCount} rarity market${activeCount === 1 ? "" : "s"} selected` : "Choose rarity markets"} open={disclosureOpen ?? internalOpen} onOpenChange={(open) => { if (disclosureOpen === undefined) setInternalOpen(open); onDisclosureChange?.(open); }} search={search} onSearchChange={setSearch} searchPlaceholder="Search all rarities…" options={presented} emptyCopy="No matching rarity." actionLabel={canCompare ? "+ Compare" : "View"} onOptionAction={toggle} message={message} />;
}
