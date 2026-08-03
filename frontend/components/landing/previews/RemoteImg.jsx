"use client";

import { useState } from "react";

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
export default function RemoteImg({ src, alt = "", className, width, height, loading = "lazy", fallback = null }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) return fallback;

  return (
    /* Remote art with no next/image remote patterns configured — the same plain
       <img> the set and Explore surfaces use. */
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
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
