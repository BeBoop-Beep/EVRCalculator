"use client";
import { useEffect, useMemo, useState } from "react";
import MarketExplorerExactItemPicker from "./MarketExplorerExactItemPicker";
import { normalizeQuerySpec, QUERY_MEMBERSHIP_EXPLICIT, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION } from "@/lib/explore/marketExplorerQuery.mjs";

function editItems(series) {
  const spec = series?.spec;
  if (!spec || spec.membershipMode !== QUERY_MEMBERSHIP_EXPLICIT) return [];
  if (spec.contractVersion === MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION) {
    const metadata = new Map((series.exactItems || []).map((item) => [item.instrumentId, item]));
    return (spec.instrumentIds || []).map((instrumentId) => ({ ...(metadata.get(instrumentId) || {}), asset: spec.asset, instrumentId }));
  }
  const metadata = new Map((series.exactItems || []).map((item) => [`${item.asset}:${item.instrumentId}`, item]));
  return (spec.instruments || []).map((item) => ({ ...(metadata.get(`${item.asset}:${item.instrumentId}`) || {}), ...item }));
}

export default function MarketExplorerExactBasket({ currentPlan, editingSeries, onAddQuery, onUpdateQuery, onCancelEdit }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const premium = currentPlan === "premium";
  const editingExact = editingSeries?.spec?.membershipMode === QUERY_MEMBERSHIP_EXPLICIT;
  useEffect(() => { if (editingExact) { setItems(editItems(editingSeries)); setOpen(true); setMessage(""); } }, [editingExact, editingSeries?.instanceId]);
  const spec = useMemo(() => { try { return normalizeQuerySpec({ membershipMode: QUERY_MEMBERSHIP_EXPLICIT, instruments: items }); } catch { return null; } }, [items]);
  const build = async (saveAsNew = false) => {
    if (!premium) { setStatus("locked"); setMessage("Exact Basket requires Index Premium."); return; }
    if (!spec) return;
    setStatus("building"); setMessage("");
    try {
      const outcome = editingExact && !saveAsNew ? await onUpdateQuery?.(editingSeries.instanceId, spec, { exactItems: items }) : await onAddQuery?.(spec, { exactItems: items });
      setStatus("success"); setMessage(outcome === "updated" ? "Basket updated." : outcome === "duplicate" ? "This basket is already active." : "Basket added to comparison.");
      if (outcome !== "duplicate") { setOpen(false); if (editingExact) onCancelEdit?.(); }
    } catch (error) { setStatus("error"); setMessage(error?.message || "Unable to build Exact Basket."); }
  };
  return <section data-market-explorer-exact-basket className="px-4 py-3"><div className="flex items-center gap-3"><div className="flex-1"><h2 className="text-sm font-semibold">Exact Basket <span className="text-[10px] text-[var(--text-secondary)]">Premium</span></h2><p className="text-xs text-[var(--text-secondary)]">Choose 1–25 Cards and Sealed Products. Each selected leaf contributes one physical unit.</p></div><button type="button" data-market-exact-open disabled={!premium} onClick={() => setOpen(true)} className="min-h-11 rounded-md border px-4">{premium ? "Create Exact Basket" : "Requires Premium"}</button></div>
    <MarketExplorerExactItemPicker open={open} selectedItems={items} onChange={setItems} onClose={() => setOpen(false)} onCancelEdit={editingExact ? () => { setOpen(false); onCancelEdit?.(); } : null} onBuild={() => build(false)} onSaveAsNew={editingExact ? () => build(true) : null} buildLabel={editingExact ? "Update Basket" : "Build Basket"} buildStatus={status} buildMessage={message} executionLocked={!premium} />
  </section>;
}
