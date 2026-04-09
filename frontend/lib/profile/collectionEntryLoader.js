import { cache } from "react";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

function toTrimmedString(value) {
  if (typeof value !== "string") return "";
  return value.trim();
}

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toCurrencyLabel(value) {
  const numeric = toNumber(value, 0);
  return `$${numeric.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function buildApiUrl(path) {
  if (typeof window !== "undefined") {
    return path;
  }

  const fallbackBaseUrl = process.env.NEXT_PUBLIC_BASE_URL
    || process.env.NEXT_PUBLIC_API_URL
    || "http://localhost:3000";
  const baseUrl = fallbackBaseUrl.endsWith("/") ? fallbackBaseUrl : `${fallbackBaseUrl}/`;
  return new URL(path.startsWith("/") ? path.slice(1) : path, baseUrl).toString();
}

async function getCookieHeader() {
  if (typeof window !== "undefined") {
    return null;
  }

  try {
    const { headers } = await import("next/headers");
    const requestHeaders = await headers();
    return requestHeaders.get("cookie");
  } catch {
    return null;
  }
}

async function fetchCollectionPayload(path) {
  console.info("[public-collection-loader] fetch_start", { path });
  const cookieHeader = await getCookieHeader();
  const requestHeaders = {
    Accept: "application/json",
  };

  if (cookieHeader) {
    requestHeaders.cookie = cookieHeader;
  }

  const response = await fetch(buildApiUrl(path), {
    method: "GET",
    headers: requestHeaders,
    cache: "no-store",
    credentials: "include",
  });

  console.info("[public-collection-loader] fetch_response", {
    path,
    status: response.status,
    ok: response.ok,
    correlationId: response.headers.get("x-correlation-id") || null,
  });

  if (!response.ok) {
    const error = new Error(`Collection request failed (${response.status})`);
    error.status = response.status;
    error.path = path;
    throw error;
  }

  return response.json();
}

function mapBackendCollectionItemToView(item, isPublic) {
  const collectibleType = item?.collectible_type || "card";
  const setName = toTrimmedString(item?.set_name) || "Unknown Set";
  const name = toTrimmedString(item?.name) || "Unknown Item";
  const rarity = toTrimmedString(item?.rarity);
  const printingType = toTrimmedString(item?.printing_type);
  const condition = toTrimmedString(item?.condition);

  const imageUrl =
    toTrimmedString(item?.image_url)
    || toTrimmedString(item?.imageUrl)
    || toTrimmedString(item?.image?.small)
    || null;
  const imageLargeUrl =
    toTrimmedString(item?.image_large_url)
    || toTrimmedString(item?.imageLargeUrl)
    || toTrimmedString(item?.image?.large)
    || null;
  const estimatedValue = toNumber(item?.estimated_value, 0);
  const valueLabel = toCurrencyLabel(estimatedValue);

  const mapped = {
    id: String(item?.id || ""),
    collectible_type: collectibleType,
    collectible_id: item?.collectible_id,
    quantity: toNumber(item?.quantity, 0),
    name,
    set: setName,
    cardNumber: item?.card_number || null,
    condition: condition || null,
    imageUrl,
    imageLargeUrl,
    valueLabel,
    estimated_value: valueLabel,
    isFoil: printingType.toLowerCase().includes("holo"),
    rarity: rarity || null,
    gradingLabel: collectibleType === "graded_card" ? condition || null : null,
    productType: collectibleType === "sealed_product" ? (toTrimmedString(item?.special_type) || "Sealed Product") : null,
    context: `${setName} • ${rarity || condition || "Collectible"}`,
  };

  if (isPublic) {
    return mapped;
  }

  return {
    ...mapped,
    user_id: item?.user_id || null,
    purchase_price: toNumber(item?.purchase_price, 0),
    cost_basis: toNumber(item?.cost_basis, 0),
    roi: toNumber(item?.roi, 0),
    unrealized_gain: toNumber(item?.unrealized_gain, 0),
    acquisition_date: item?.acquisition_date || null,
    fees_taxes: toNumber(item?.fees_taxes, 0),
    notes: item?.notes || null,
  };
}

async function fetchPrivateCollectionEntriesFromApi() {
  const payload = await fetchCollectionPayload("/api/my-collection/dashboard?include_collection_items=1");
  const items = Array.isArray(payload?.collection_items) ? payload.collection_items : [];
  return items.map((item) => mapBackendCollectionItemToView(item, false));
}

async function fetchPublicCollectionEntriesFromApi(username) {
  const encodedUsername = encodeURIComponent(String(username || "").trim());
  const payload = await fetchCollectionPayload(`/api/public-profile/${encodedUsername}/collection-summary?include_collection_items=1`);
  const items = Array.isArray(payload?.collection_items) ? payload.collection_items : [];
  console.info("[public-collection-loader] raw_items", {
    username: String(username || "").trim(),
    rawCount: items.length,
    byType: items.reduce((acc, item) => {
      const key = String(item?.collectible_type || "unknown");
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {}),
    itemMeta: items.map((item) => ({
      id: String(item?.id || ""),
      type: String(item?.collectible_type || ""),
      collectibleId: String(item?.collectible_id || ""),
    })),
  });
  const mappedItems = items.map((item) => mapBackendCollectionItemToView(item, true));
  console.info("[public-collection-loader] transformed_items", {
    username: String(username || "").trim(),
    transformedCount: mappedItems.length,
  });
  return mappedItems;
}

function seededFloat(seed) {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function seededInt(seed, min, max) {
  return Math.floor(seededFloat(seed) * (max - min + 1)) + min;
}

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function createPublicCollectionItems(username, count = 16) {
  const baseSeed = Array.from(username || "collector").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const sets = ["Scarlet & Violet", "Sword & Shield", "Sun & Moon", "X & Y", "Black & White"];
  const cardNames = [
    "Charizard EX",
    "Blastoise GX",
    "Venusaur V",
    "Pikachu VMAX",
    "Mewtwo EX",
    "Alakazam GX",
    "Dragonite V",
    "Gyarados VMAX",
    "Articuno EX",
    "Zapdos V",
    "Moltres GX",
    "Lugia VMAX",
  ];

  return Array.from({ length: count }, (_, index) => {
    const seed = baseSeed + index * 17;
    const isSealed = index % 5 === 0;
    const setName = sets[seededInt(seed + 1, 0, sets.length - 1)];
    const cardName = cardNames[seededInt(seed + 2, 0, cardNames.length - 1)];
    return {
      id: `collection-${index}`,
      collectible_type: isSealed ? "sealed_product" : "card",
      collectible_id: isSealed ? `sealed-${index + 1}` : `card-${index + 1}`,
      name: isSealed ? `Booster Box - ${setName}` : cardName,
      set: setName,
      cardNumber: isSealed ? null : `${index + 1}/${seededInt(seed + 3, 100, 300)}`,
      context: isSealed ? `${setName} • Sealed Product` : `${setName} • Holo Rare`,
      valueLabel: `$${seededInt(seed + 4, 50, 550)}`,
      estimated_value: `$${seededInt(seed + 4, 50, 550)}`,
      isFoil: seededFloat(seed + 5) > 0.7,
      quantity: seededInt(seed + 10, 1, 3),
      condition: isSealed ? "Sealed" : ["NM", "LP", "MP", "HP"][seededInt(seed + 6, 0, 3)],
      imageUrl: null,
      productType: isSealed ? "Booster Box" : null,
      rarity: seededFloat(seed + 7) > 0.7 ? "Ultra Rare" : "Rare",
      gradingLabel: seededFloat(seed + 8) > 0.8 ? `PSA ${seededInt(seed + 9, 8, 10)}` : null,
    };
  });
}

function createPrivateCollectionItems() {
  return [
    {
      id: "1",
      user_id: "owner-1",
      collectible_type: "card",
      collectible_id: "card-1",
      name: "Pikachu ex",
      set: "Scarlet & Violet",
      cardNumber: "025/102",
      condition: "Near Mint",
      imageUrl: null,
      valueLabel: "$45.50",
      estimated_value: "$45.50",
      isFoil: false,
      rarity: "Rare",
      gradingLabel: null,
      productType: null,
      quantity: 1,
      purchase_price: 32.25,
      cost_basis: 32.25,
      roi: 41.09,
      unrealized_gain: 13.25,
      acquisition_date: "2025-09-14",
      fees_taxes: 0,
      notes: "Pulled from booster pack.",
    },
    {
      id: "2",
      user_id: "owner-1",
      collectible_type: "card",
      collectible_id: "card-2",
      name: "Charizard ex",
      set: "Scarlet & Violet",
      cardNumber: "003/102",
      condition: "Mint",
      imageUrl: null,
      valueLabel: "$120.00",
      estimated_value: "$120.00",
      isFoil: true,
      rarity: "Ultra Rare",
      gradingLabel: "PSA 10",
      productType: null,
      quantity: 1,
      purchase_price: 79,
      cost_basis: 79,
      roi: 51.9,
      unrealized_gain: 41,
      acquisition_date: "2025-05-11",
      fees_taxes: 0,
      notes: "Bought at regional show.",
    },
    {
      id: "3",
      user_id: "owner-1",
      collectible_type: "sealed_product",
      collectible_id: "sealed-1",
      name: "Booster Box - Scarlet & Violet",
      set: "Scarlet & Violet",
      productType: "Booster Box",
      condition: "Sealed",
      imageUrl: null,
      valueLabel: "$89.99",
      estimated_value: "$89.99",
      isFoil: false,
      rarity: null,
      gradingLabel: null,
      cardNumber: null,
      quantity: 2,
      purchase_price: 75,
      cost_basis: 150,
      roi: 19.99,
      unrealized_gain: 29.98,
      acquisition_date: "2025-07-02",
      fees_taxes: 3.5,
      notes: "Sealed case break remainder.",
    },
    {
      id: "4",
      user_id: "owner-1",
      collectible_type: "card",
      collectible_id: "card-4",
      name: "Blastoise",
      set: "Base Set",
      cardNumber: "002/102",
      condition: "Lightly Played",
      imageUrl: null,
      valueLabel: "$15.00",
      estimated_value: "$15.00",
      isFoil: false,
      rarity: "Rare",
      gradingLabel: null,
      productType: null,
      quantity: 1,
      purchase_price: 11,
      cost_basis: 11,
      roi: 36.36,
      unrealized_gain: 4,
      acquisition_date: "2025-08-21",
      fees_taxes: 0,
      notes: "Childhood binder copy.",
    },
  ];
}

function stripPortfolioFields(entry) {
  if (!entry) return null;
  const {
    purchase_price,
    cost_basis,
    roi,
    unrealized_gain,
    acquisition_date,
    fees_taxes,
    notes,
    user_id,
    ...safeEntry
  } = entry;
  return safeEntry;
}

export function buildCollectionStats(items) {
  const totalValue = items.reduce((sum, item) => sum + parseCurrencyValue(item.valueLabel), 0);
  const investedValue = items.reduce((sum, item) => {
    const parsedCostBasis = Number(item?.cost_basis);
    const currentValue = parseCurrencyValue(item.valueLabel);
    const base = Number.isFinite(parsedCostBasis) && parsedCostBasis > 0
      ? parsedCostBasis
      : currentValue * 0.84;
    return sum + base;
  }, 0);
  const sealedItems = items.filter((item) => item.productType || !item.cardNumber);
  const cardItems = items.filter((item) => item.cardNumber && !item.productType);
  const gradedItems = items.filter((item) => Boolean(item.gradingLabel));

  return {
    totalItems: items.length,
    totalValue: `$${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    investedValue: `$${investedValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    sealedCount: sealedItems.length,
    cardsCount: cardItems.length,
    gradedCount: gradedItems.length,
    config: {
      itemsLabel: "Total Items",
      valueLabel: "Collection Value",
      sealedLabel: "Sealed Products",
    },
  };
}

export const getPrivateCollectionEntries = cache(async function getPrivateCollectionEntries() {
  try {
    const items = await fetchPrivateCollectionEntriesFromApi();
    return items;
  } catch {
    return [];
  }
});

const getPublicCollectionEntriesPerRequest = cache(async function getPublicCollectionEntriesPerRequest(usernameParam) {
  const username = String(usernameParam || "").trim();
  try {
    const items = await fetchPublicCollectionEntriesFromApi(username);
    const sanitizedItems = items.map(stripPortfolioFields);
    const idList = sanitizedItems.map((item) => String(item?.id || "")).filter(Boolean);
    const duplicateIds = idList.filter((id, index) => idList.indexOf(id) !== index);

    console.info("[public-collection-lifecycle] loader_to_page", {
      username,
      count: sanitizedItems.length,
      ids: idList,
      duplicateIds,
      itemMeta: sanitizedItems.map((item) => ({
        id: String(item?.id || ""),
        type: String(item?.collectible_type || ""),
        name: String(item?.name || ""),
      })),
    });

    return sanitizedItems;
  } catch (error) {
    console.error("[public-collection-loader] fetch_failed", {
      username,
      message: error instanceof Error ? error.message : String(error),
      status: error?.status || null,
      path: error?.path || null,
    });
    throw error;
  }
});

export async function getPublicCollectionEntries(username) {
  return getPublicCollectionEntriesPerRequest(String(username || "").trim());
}

export const getPrivateCollectionEntryById = cache(async function getPrivateCollectionEntryById(entryId) {
  const entries = await getPrivateCollectionEntries();
  return entries.find((entry) => String(entry.id) === String(entryId)) || null;
});

export const getPublicCollectionEntryById = cache(async function getPublicCollectionEntryById(username, entryId) {
  const entries = await getPublicCollectionEntries(username);
  return entries.find((entry) => String(entry.id) === String(entryId)) || null;
});

export async function getCollectionEntryDetailById({ mode, entryId, username = "" }) {
  if (mode === "public") {
    const [items, context] = await Promise.all([
      getPublicCollectionEntries(username),
      getCachedPublicRouteContextByUsername(username || ""),
    ]);

    const entry = items.find((item) => String(item.id) === String(entryId));
    return {
      entry: stripPortfolioFields(entry) || null,
      ownerLabel: context.identity.displayName || context.identity.username,
      canManage: false,
    };
  }

  const items = await getPrivateCollectionEntries();
  const entry = items.find((item) => String(item.id) === String(entryId));

  return {
    entry: entry || null,
    ownerLabel: "My Collection",
    canManage: true,
  };
}
