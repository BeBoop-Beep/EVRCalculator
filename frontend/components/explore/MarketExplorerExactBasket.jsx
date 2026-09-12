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

export default function MarketExplorerExactBasket({ currentPlan, editingSeries, onAddQuery, onUpdateQuery, onCancelEdit, onClose }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const premium = currentPlan === "premium";
  const editingExact = editingSeries?.spec?.membershipMode === QUERY_MEMBERSHIP_EXPLICIT;
  useEffect(() => {
    if (!editingExact) return;
    setItems(editItems(editingSeries));
    setMessage("");
  }, [editingExact, editingSeries]);
  const spec = useMemo(() => { try { return normalizeQuerySpec({ membershipMode: QUERY_MEMBERSHIP_EXPLICIT, instruments: items }); } catch { return null; } }, [items]);
  const build = async (saveAsNew = false) => {
    if (!premium) { setStatus("locked"); setMessage("Build Your Market requires Index Premium."); return; }
    if (!spec) return;
    setStatus("building"); setMessage("");
    try {
      const outcome = editingExact && !saveAsNew ? await onUpdateQuery?.(editingSeries.instanceId, spec, { exactItems: items }) : await onAddQuery?.(spec, { exactItems: items });
      setStatus("success");
      setMessage(outcome === "updated" ? "Market updated." : outcome === "duplicate" ? "This market is already active." : "Market added to comparison.");
      if (outcome !== "duplicate") {
        if (editingExact) onCancelEdit?.();
        else setItems([]);
        onClose?.();
      }
    } catch (error) { setStatus("error"); setMessage(error?.message || "Unable to build your market."); }
  };
  const cancelEdit = editingExact ? () => { onCancelEdit?.(); onClose?.(); } : null;
  return <MarketExplorerExactItemPicker selectedItems={items} onChange={setItems} onClose={onClose} onCancelEdit={cancelEdit} onBuild={() => build(false)} onSaveAsNew={editingExact ? () => build(true) : null} buildLabel={editingExact ? "Update Market" : "Build Market"} buildStatus={status} buildMessage={message} executionLocked={!premium} />;
}
