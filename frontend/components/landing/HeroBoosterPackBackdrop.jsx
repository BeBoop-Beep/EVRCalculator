import RemoteImg from "./previews/RemoteImg";
import { SET_LOGO_WIDTH } from "@/lib/images/remoteImageDelivery.mjs";
import styles from "./LandingHero.module.css";

/**
 * Atmospheric product imagery behind the hero: a single booster pack, treated
 * as a lit silhouette rather than as a foreground card.
 *
 * PURELY DECORATIVE. It takes an already-resolved image — it never fetches —
 * is `aria-hidden`, carries an empty alt, and is `pointer-events: none`, so it
 * is absent from the accessibility tree and cannot intercept a click on the
 * CTAs or the Live Set Intelligence panel above it. It is absolutely positioned
 * inside the hero's existing clipping boundary, so it adds no height and cannot
 * shift layout.
 *
 * Desktop and mobile are two independently authored placements in the stylesheet
 * (not one composition scaled down): see `.packBackdrop` and its `max-width`
 * blocks in LandingHero.module.css.
 *
 * Renders nothing when no image resolved, which is the documented step-4
 * fallback — the hero keeps its current composition.
 */
export default function HeroBoosterPackBackdrop({ image }) {
  const src = typeof image?.src === "string" ? image.src.trim() : "";
  if (!src) return null;

  return (
    <div className={styles.packBackdrop} aria-hidden="true">
      <RemoteImg
        src={src}
        alt=""
        className={styles.packBackdropImg}
        loading="lazy"
        /* The one slot on this page that is painted large rather than as a
           mark or thumbnail, so it asks the optimizer for more width. */
        optimizeWidth={SET_LOGO_WIDTH}
        /* A dead URL collapses to nothing rather than to a broken-image glyph;
           RemoteImg returns the fallback, which here is deliberately null. */
        fallback={null}
      />
    </div>
  );
}
