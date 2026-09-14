import { buildQueryKey, normalizeQuerySpec } from "./marketExplorerQuery.mjs";

let sequence = 0;

export function createMarketInstanceId() {
  sequence += 1;
  if (globalThis.crypto?.randomUUID) return `market:${globalThis.crypto.randomUUID()}`;
  return `market:${Date.now().toString(36)}:${sequence.toString(36)}`;
}

export function specsAreEquivalent(left, right) {
  if (!left || !right) return false;
  try { return buildQueryKey(left) === buildQueryKey(right); } catch { return false; }
}

export function attachMarketInstance(series, { instanceId = createMarketInstanceId(), exactItems = [] } = {}) {
  const label = exactBasketLabel(exactItems, series.asset);
  return {
    ...series,
    instanceId,
    key: instanceId,
    sourceType: "query",
    spec: normalizeQuerySpec(series.spec),
    exactItems: Array.isArray(exactItems) ? exactItems : [],
    ...(label ? { label, shortLabel: label } : {}),
  };
}

export function replaceMarketInstance(current, result, { exactItems = [] } = {}) {
  const label = exactBasketLabel(exactItems, result.asset);
  return {
    ...result,
    instanceId: current.instanceId,
    key: current.key,
    sourceType: "query",
    color: current.color,
    softColor: current.softColor,
    exactItems: Array.isArray(exactItems) ? exactItems : [],
    ...(label ? { label, shortLabel: label } : {}),
  };
}

export function exactBasketLabel(items, asset = "cards") {
  if (!Array.isArray(items) || !items.length) return null;
  if (items.length === 1) {
    const item = items[0];
    return [item.name, item.setName, item.edition || item.variantLabel].filter(Boolean).join(" · ");
  }
  if (items.length === 2) return items.map((item) => item.name).join(" + ");
  return `${items.length}-${asset === "sealed" ? "Product" : "Card"} Custom Basket`;
}
