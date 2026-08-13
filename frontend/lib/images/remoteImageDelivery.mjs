/**
 * Optimized delivery for third-party card/set artwork.
 *
 * `images.pokemontcg.io` publishes exactly two variants per card — `<n>.png`
 * (245x342, ~182 kB) and `<n>_hires.png` (~1.2 MB) — and one `logo.png` per set
 * (~85-160 kB). The app already asks for the smaller of the two, so there is no
 * smaller upstream variant left to pick: the only remaining lever is to
 * transcode. Those PNGs are painted into slots as small as 40x54 CSS px, where
 * a WebP at the real slot width is ~2 kB instead of ~182 kB.
 *
 * Rather than migrate a dozen `<img>` call sites (each with its own wrapper,
 * `object-contain`/`object-cover` and absolute positioning) to `next/image` and
 * risk moving the layout, this builds the `/_next/image` URL those components
 * would have requested anyway and leaves the elements — and therefore the
 * rendered geometry — untouched.
 *
 * Two rules keep this honest:
 *
 *  1. A source this cannot optimize is returned UNCHANGED. An unknown host, a
 *     relative path, a data: URI or a malformed URL must keep working exactly
 *     as it does today rather than 400 through the optimizer.
 *  2. Widths are snapped to Next's configured buckets. `/_next/image` rejects a
 *     width that is not in `deviceSizes ∪ imageSizes`, and snapping also means
 *     two components that render the same artwork at similar sizes request the
 *     SAME url and share one cache entry instead of forcing two transforms.
 */

// `next.config.mjs` leaves both lists at their defaults, so these are Next's
// own defaults. If either is ever customised there, update this list with it.
const IMAGE_SIZES = [16, 32, 48, 64, 96, 128, 256, 384];
const DEVICE_SIZES = [640, 750, 828, 1080, 1200, 1920, 2048, 3840];
const ALLOWED_WIDTHS = [...IMAGE_SIZES, ...DEVICE_SIZES];

// Must stay in sync with `images.remotePatterns` in next.config.mjs. A host
// present here but absent there produces a 400 from the optimizer.
const OPTIMIZABLE_HOSTS = new Set(["images.pokemontcg.io", "images.scrydex.com"]);

// Next's default quality. Declaring a different one would require an
// `images.qualities` entry in next.config.mjs, so this deliberately does not.
const DEFAULT_QUALITY = 75;

/*
 * Width policy.
 *
 * These are shared constants rather than per-call-site numbers on purpose: a
 * width is also a cache key, so two components painting the SAME artwork at
 * similar sizes must ask for the same width or the page pays for two
 * transforms and two round trips where it previously paid for one.
 *
 * Both source images top out well below these numbers (card art is 245 px
 * wide, set logos ~451 px) and the optimizer never upscales, so each of these
 * is "the source at its native resolution, transcoded" — the byte saving comes
 * from PNG -> WebP/AVIF, not from throwing pixels away.
 */

/** Card art in the checklist grid and the largest top-chase thumbnail (68 CSS px at 2x). */
export const CARD_ART_WIDTH = 256;

/** Card thumbnails in rows, tickers and detail strips — 64 CSS px or less. */
export const CARD_THUMBNAIL_WIDTH = 128;

/** Large set logo slots: catalog tiles, catalog ambient wash, set hero, page atmosphere. */
export const SET_LOGO_WIDTH = 640;

/**
 * Set logos painted into dense list/table rows — the 32 CSS px Rankings slot and
 * the 24 CSS px Market ladder slot. 96 covers the larger of the two at DPR 3.
 *
 * This is deliberately NOT SET_LOGO_WIDTH. Source logos are ~440-543 px wide, so
 * the optimizer never upscales and a w=640 request means "the whole logo,
 * transcoded" — 17-30 kB per set. The same logo at w=96 is ~2-3.4 kB. A 32 px
 * slot cannot show the difference, but a Rankings page paints 22 of them, so the
 * shared-hero cache key was buying a possible cache hit for visitors who arrived
 * from a set page at the cost of ~7x the bytes and a full-resolution cold
 * transform for everyone else.
 *
 * Still ONE shared constant, not a per-call-site number: Rankings and the Market
 * ladder paint the same set logos, so they must request the same width to share
 * a single transform.
 */
export const SET_LOGO_THUMBNAIL_WIDTH = 96;

/**
 * Snap a requested width up to the smallest configured bucket that covers it.
 * Requests larger than the largest bucket clamp to it rather than being
 * rejected by the optimizer.
 */
export function snapImageWidth(width) {
  const requested = Number(width);
  if (!Number.isFinite(requested) || requested <= 0) return null;
  return ALLOWED_WIDTHS.find((allowed) => allowed >= requested) ?? ALLOWED_WIDTHS[ALLOWED_WIDTHS.length - 1];
}

export function isOptimizableImageSource(src) {
  if (typeof src !== "string" || src.length === 0) return false;
  let parsed;
  try {
    parsed = new URL(src);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") return false;
  return OPTIMIZABLE_HOSTS.has(parsed.hostname);
}

/**
 * The `/_next/image` URL for `src` at `width`, or `src` unchanged when it is
 * not something this origin is configured to optimize.
 */
export function optimizedImageUrl(src, width, quality = DEFAULT_QUALITY) {
  if (!isOptimizableImageSource(src)) return src;
  const snapped = snapImageWidth(width);
  if (snapped === null) return src;
  return `/_next/image?url=${encodeURIComponent(src)}&w=${snapped}&q=${quality}`;
}

/**
 * A `srcSet` across several widths for slots whose CSS width is responsive.
 * Returns `undefined` (not an empty string) for non-optimizable sources so the
 * attribute is omitted rather than emitted empty.
 */
export function optimizedImageSrcSet(src, widths, quality = DEFAULT_QUALITY) {
  if (!isOptimizableImageSource(src) || !Array.isArray(widths)) return undefined;
  const snapped = [...new Set(widths.map(snapImageWidth).filter((w) => w !== null))].sort((a, b) => a - b);
  if (snapped.length === 0) return undefined;
  return snapped.map((w) => `${optimizedImageUrl(src, w, quality)} ${w}w`).join(", ");
}
