import { getPrivateCollectionEntries } from "@/lib/profile/collectionEntryLoader";

const PORTFOLIO_KEYS = new Set([
  "purchase_price",
  "cost_basis",
  "roi",
  "unrealized_gain",
  "acquisition_date",
  "fees_taxes",
  "notes",
  "user_id",
]);

function getMarketSnapshot(seedValue) {
  const base = Number(seedValue % 300) + 25;
  return {
    market_price: Number(base.toFixed(2)),
    estimated_value: Number((base * 1.02).toFixed(2)),
    liquidity_indicator: base > 150 ? "high" : base > 80 ? "moderate" : "low",
    price_trend: [
      Number((base * 0.91).toFixed(2)),
      Number((base * 0.95).toFixed(2)),
      Number((base * 0.97).toFixed(2)),
      Number(base.toFixed(2)),
    ],
    historical_sales: [
      { date: "2026-01-10", price: Number((base * 0.92).toFixed(2)) },
      { date: "2026-02-10", price: Number((base * 0.95).toFixed(2)) },
      { date: "2026-03-10", price: Number((base * 1.01).toFixed(2)) },
    ],
  };
}

function stableSeed(value) {
  return String(value || "collectible")
    .split("")
    .reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function sanitizeMarketOnly(payload) {
  if (!payload || typeof payload !== "object") return payload;
  const clone = { ...payload };
  for (const key of Object.keys(clone)) {
    if (PORTFOLIO_KEYS.has(key)) {
      delete clone[key];
    }
  }
  return clone;
}

export function assertNoPortfolioFields(payload, sourceLabel) {
  if (!payload || typeof payload !== "object") return;
  for (const key of Object.keys(payload)) {
    if (PORTFOLIO_KEYS.has(key)) {
      throw new Error(`Public market payload leak detected in ${sourceLabel}: ${key}`);
    }
  }
}

export async function getCardMarketPageData(cardId) {
  const entries = await getPrivateCollectionEntries();
  const fromEntry = entries.find((entry) => entry.collectible_type === "card" && String(entry.collectible_id) === String(cardId));
  const seed = stableSeed(cardId);

  const metadata = {
    card_id: String(cardId),
    name: fromEntry?.name || `Card ${cardId}`,
    set_name: fromEntry?.set || "Unknown Set",
    card_number: fromEntry?.cardNumber || "-",
    rarity: fromEntry?.rarity || "Unknown",
    collectible_type: "card",
  };

  const payload = {
    metadata,
    market: getMarketSnapshot(seed),
  };

  assertNoPortfolioFields(payload, "getCardMarketPageData");
  return sanitizeMarketOnly(payload);
}

export async function getSealedProductMarketPageData(productId) {
  const entries = await getPrivateCollectionEntries();
  const fromEntry = entries.find(
    (entry) => entry.collectible_type === "sealed_product" && String(entry.collectible_id) === String(productId)
  );
  const seed = stableSeed(productId);

  const metadata = {
    product_id: String(productId),
    name: fromEntry?.name || `Sealed Product ${productId}`,
    product_type: fromEntry?.productType || "Sealed Product",
    set_name: fromEntry?.set || "Unknown Set",
    collectible_type: "sealed_product",
  };

  const payload = {
    metadata,
    market: getMarketSnapshot(seed),
  };

  assertNoPortfolioFields(payload, "getSealedProductMarketPageData");
  return sanitizeMarketOnly(payload);
}
