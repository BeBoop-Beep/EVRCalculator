// ---------------------------------------------------------------------------
// Market Explorer constituent row presentation: image, detail route, preview.
//
// ROW-DRIVEN, NEVER LABEL-DRIVEN. Nothing here special-cases a market (Fossil,
// Rare Ultra, Sets, Rarities...). A row either carries the fields or it does not.
// ---------------------------------------------------------------------------
import { buildPokemonCardDetailHref } from "../pokemon/pokemonCardDetailClient.js";
import { buildSealedProductHref } from "../pokemon/sealedProductRoutes.mjs";
import { resolveVariantLabel } from "./marketExplorerConstituents.mjs";

const usable = (value) => {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

/**
 * ONE image resolver. Supports imageSmallUrl / imageUrl / imageLargeUrl
 * (existing and future fields).
 *
 *  - `thumbUrl`   for the row: prefers the SMALL image, so a table never loads
 *                 high-resolution art per row. Larger fields are only a fallback
 *                 when nothing smaller exists.
 *  - `previewUrl` for the hover preview: large -> standard -> small.
 *  - no image     -> `hasImage: false`; callers render a neutral placeholder.
 */
export function resolveConstituentImage(row) {
  const small = usable(row?.imageSmallUrl);
  const standard = usable(row?.imageUrl);
  const large = usable(row?.imageLargeUrl);
  const thumbUrl = small || standard || large || null;
  const previewUrl = large || standard || small || null;
  return { hasImage: Boolean(thumbUrl), thumbUrl, previewUrl };
}

/**
 * ONE detail-route resolver. Identity fields only, never labels.
 *
 *  - sealed row (sealedProductId)  -> the existing /sealed-products/[id] route;
 *  - card row (canonicalCardId + a set identity the routing helper accepts)
 *                                  -> the existing Pokemon card detail route.
 * Anything that cannot resolve returns null so no link is rendered.
 */
export function resolveConstituentDetailHref(row) {
  if (!row || typeof row !== "object") return null;
  if (usable(String(row.sealedProductId ?? ""))) return buildSealedProductHref({ sealedProductId: row.sealedProductId });
  if (!usable(String(row.canonicalCardId ?? ""))) return null;
  return buildPokemonCardDetailHref({
    setName: row.setName, setId: row.setId,
    canonicalCardId: row.canonicalCardId, cardVariantId: row.cardVariantId,
  });
}

export const constituentRowName = (row) => row?.cardName || row?.productName || row?.name || "constituent";

const priceText = (value, formatPrice) => (formatPrice ? formatPrice(value) : String(value ?? "—"));

/**
 * The preview's content model. Compact on purpose — it never dumps raw
 * metadata. Extensible: a future asset kind (graded) adds one branch here and
 * the preview component does not change.
 */
export function buildConstituentPreviewModel(row, { asset = "cards", formatPrice } = {}) {
  const image = resolveConstituentImage(row);
  const fields = [];
  const push = (label, value) => { if (value !== null && value !== undefined && value !== "") fields.push({ label, value }); };
  const isSealed = asset === "sealed" || Boolean(row?.sealedProductId);
  if (isSealed) {
    push("Set", row?.setName);
    push("Market price", row?.marketPrice == null ? null : priceText(row.marketPrice, formatPrice));
    push("Product family", row?.productFamilyLabel);
    push("Variant", row?.variantLabel || row?.productVariantLabel);
  } else {
    push("Set", row?.setName);
    push("Market price", row?.marketPrice == null ? null : priceText(row.marketPrice, formatPrice));
    push("Rarity", row?.rarity);
    push("Edition", row?.edition);
    push("Printing", resolveVariantLabel(row));
  }
  return { kind: isSealed ? "sealed" : "card", title: constituentRowName(row), image, fields };
}

/**
 * Fixed-position placement for the hover preview so a table's overflow never
 * clips it. Prefers the right of the thumbnail, flips to the left when the right
 * side does not fit, and clamps vertically inside the viewport.
 */
export function positionConstituentPreview(anchor, size, viewport, gap = 10, margin = 8) {
  const width = size.width;
  const height = Math.min(size.height, Math.max(0, viewport.height - margin * 2));
  const fitsRight = anchor.right + gap + width <= viewport.width - margin;
  const fitsLeft = anchor.left - gap - width >= margin;
  const placement = fitsRight || !fitsLeft ? "right" : "left";
  let left = placement === "right" ? anchor.right + gap : anchor.left - gap - width;
  left = Math.max(margin, Math.min(left, viewport.width - margin - width));
  const centered = anchor.top + (anchor.bottom - anchor.top) / 2 - height / 2;
  const top = Math.max(margin, Math.min(centered, viewport.height - margin - height));
  return { left, top, width, maxHeight: height, placement };
}
