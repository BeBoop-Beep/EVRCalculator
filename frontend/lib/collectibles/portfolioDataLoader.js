import { getAuthenticatedUserFromCookies } from "@/lib/authServer";
import {
  getPrivateCollectionEntryById,
  getPublicCollectionEntryById,
} from "@/lib/profile/collectionEntryLoader";
import {
  getCardMarketPageData,
  getSealedProductMarketPageData,
} from "@/lib/collectibles/marketDataLoader";

function mapViewerId(user) {
  return user?.id || user?.userId || user?.sub || null;
}

function calculateHoldingDurationDays(acquisitionDate) {
  if (!acquisitionDate) return null;
  const start = new Date(acquisitionDate).getTime();
  if (Number.isNaN(start)) return null;
  const diff = Date.now() - start;
  return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
}

export async function getOwnedEntryPortfolioPageData(entryId) {
  const auth = await getAuthenticatedUserFromCookies();
  const entry = await getPrivateCollectionEntryById(entryId);

  if (!entry) {
    return {
      found: false,
      canViewPortfolio: false,
      market: null,
      metadata: null,
      portfolio: null,
    };
  }

  const viewerId = mapViewerId(auth.user);
  const ownerId = entry.user_id || "owner-1";
  const canViewPortfolio = Boolean(viewerId) && String(viewerId) === String(ownerId);

  const marketBundle = entry.collectible_type === "sealed_product"
    ? await getSealedProductMarketPageData(entry.collectible_id)
    : await getCardMarketPageData(entry.collectible_id);

  return {
    found: true,
    canViewPortfolio,
    metadata: {
      entry_id: String(entry.id),
      collectible_type: entry.collectible_type,
      collectible_id: entry.collectible_id,
      name: entry.name,
      set_name: entry.set,
      condition: entry.condition,
      quantity: entry.quantity,
    },
    market: marketBundle.market,
    portfolio: canViewPortfolio
      ? {
          purchase_price: entry.purchase_price,
          cost_basis: entry.cost_basis,
          current_value: Number(String(entry.valueLabel || "0").replace(/[^\d.-]/g, "")),
          unrealized_gain: entry.unrealized_gain,
          roi: entry.roi,
          acquisition_date: entry.acquisition_date,
          holding_duration_days: calculateHoldingDurationDays(entry.acquisition_date),
          notes: entry.notes,
          fees_taxes: entry.fees_taxes,
          quantity: entry.quantity,
          condition: entry.condition,
        }
      : null,
  };
}

export async function getPublicCollectionRedirectCollectible(username, entryId) {
  const publicEntry = await getPublicCollectionEntryById(username, entryId);
  if (!publicEntry) return null;
  return {
    collectible_type: publicEntry.collectible_type,
    collectible_id: publicEntry.collectible_id,
  };
}
