"use client";

import { useState } from "react";

import { CARD_ART_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";

/**
 * A remote image that degrades instead of breaking.
 *
 * Every image on this page comes from a third party — set logos and symbols
 * from images.pokemontcg.io, card art from the same host — so any of them can
 * 404 or be blocked. Without an error path those render as the browser's broken
 * -image glyph, which on a marketing page looks like the product is down.
 *
 * This is the smallest possible client island: one boolean. It exists so the
 * surrounding previews can stay server components.
 */
export default function RemoteImg({
  src,
  alt = "",
  className,
  width,
  height,
  loading = "lazy",
  fallback = null,
  // Every slot on this page paints remote art at 128 CSS px or less, so the
  // default is the card source's own native width — no upscale, no visible
  // downscale, and one shared cache entry across the marks and thumbs. Only the
  // hero backdrop is big enough to want more.
  optimizeWidth = CARD_ART_WIDTH,
}) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) return fallback;

  const deliveredSrc = optimizedImageUrl(src, optimizeWidth);

  return (
    /* Still a plain <img>: the element, its classes and its geometry are
       unchanged, and only the URL now points at the image optimizer (and only
       for the hosts `images.remotePatterns` allows — anything else is passed
       through untouched by `optimizedImageUrl`). */
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={deliveredSrc}
      alt={alt}
      className={className}
      width={width}
      height={height}
      loading={loading}
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
