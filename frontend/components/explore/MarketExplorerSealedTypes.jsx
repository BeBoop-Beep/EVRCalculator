"use client";
import React, { useMemo, useState } from "react";
import { ASSET_OPTION_ACTION, NO_APPROVED_SEALED_QUICK_COPY, approvedSealedQuickMarkets, normalizeSealedTypeOptions } from "@/lib/explore/marketExplorerAssetOptions.mjs";
import MarketExplorerAssetMarketSelector from "./MarketExplorerAssetMarketSelector";
const clean = (value) => String(value || "").trim().toLowerCase();

export default function MarketExplorerSealedTypes({ options = null, status = "ready", activeKeys = [], pendingKeys = [], canCompare = false, onSelect, onRetry, v2Mode = true, formatMarkets = [], disclosureOpen, onDisclosureChange }) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const types = useMemo(() => normalizeSealedTypeOptions(options), [options]);
  const source = v2Mode ? types : formatMarkets.map((market) => ({ id: market.market_key, label: market.label, marketKey: market.market_key, action: ASSET_OPTION_ACTION.prepared, state: "PREPARED" }));
  const presented = source.filter((type) => !clean(search) || clean(type.label).includes(clean(search))).map((type) => ({ ...type, active: Boolean(type.marketKey && activeKeys.includes(type.marketKey)), pending: Boolean(type.marketKey && pendingKeys.includes(type.marketKey)), unavailable: type.action !== ASSET_OPTION_ACTION.prepared, reason: type.action === ASSET_OPTION_ACTION.prepared ? null : (type.reason || "This Sealed Type is not published as a prepared market yet.") }));
  const activeCount = source.filter((type) => type.marketKey && activeKeys.includes(type.marketKey)).length;
  let statusContent = null;
  if (v2Mode && status === "unavailable") statusContent = <div role="alert" className="flex items-center justify-between gap-2 px-2 py-2 text-[11px] text-[var(--text-secondary)]"><span>Sealed types are temporarily unavailable.</span>{onRetry ? <button type="button" onClick={onRetry} className="rounded border border-[var(--border-subtle)] px-2 py-1 font-semibold">Retry</button> : null}</div>;
  else if (v2Mode && status === "loading" && !types.length) statusContent = <p role="status" className="px-2 py-2 text-[11px] text-[var(--text-secondary)]">Loading sealed types…</p>;
  return <MarketExplorerAssetMarketSelector disclosureId="sealed-types" heading="Sealed Types" summary={activeCount ? `${activeCount} sealed type${activeCount === 1 ? "" : "s"} selected` : "Choose sealed types"} open={disclosureOpen ?? internalOpen} onOpenChange={(open) => { if (disclosureOpen === undefined) setInternalOpen(open); onDisclosureChange?.(open); }} search={search} onSearchChange={setSearch} searchPlaceholder="Search sealed types…" options={presented} emptyCopy="No matching sealed type." statusContent={statusContent} actionLabel={canCompare ? "+ Compare" : "View"} onOptionAction={(type) => type.marketKey && onSelect?.(type.marketKey)} />;
}

export function MarketExplorerSealedQuickMarkets({ options = null, activeKeys = [], onSelect }) {
  const quick = approvedSealedQuickMarkets(options);
  return <section data-market-explorer-sealed-quick className="py-2" aria-labelledby="sealed-quick-heading"><h3 id="sealed-quick-heading" className="text-xs font-semibold text-[var(--text-primary)]">Quick Markets</h3>{quick.length ? <ul className="mt-1 space-y-1">{quick.map((q) => <li key={q.key}><button type="button" data-sealed-quick-market={q.key} aria-pressed={activeKeys.includes(q.key)} onClick={() => onSelect?.(q.key)} className="w-full rounded border border-[var(--border-subtle)] px-2 py-1.5 text-left text-xs text-[var(--text-primary)]">{q.label}</button></li>)}</ul> : <p data-sealed-quick-empty className="mt-1 text-[11px] text-[var(--text-secondary)]">{NO_APPROVED_SEALED_QUICK_COPY}</p>}</section>;
}
