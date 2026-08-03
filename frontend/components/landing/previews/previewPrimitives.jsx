import RemoteImg from "./RemoteImg";
import { getInitials, formatSignedPercent, signedCurrency0 } from "../landingFormat.mjs";
import styles from "../landing.module.css";

/**
 * Display primitives shared by the homepage previews. All server-rendered and
 * read-only — they take already-fetched values and draw them, and none of them
 * has a loading state of its own because none of them fetches.
 *
 * Every remote image goes through RemoteImg so a dead logo or card URL falls
 * back to type rather than to a broken-image glyph.
 */

export function Arrow() {
  return (
    <svg className={styles.ctaArrow} width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8h10M9 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SetMark({ logoUrl, name, className }) {
  return (
    <span className={className || styles.setMark}>
      <RemoteImg
        src={logoUrl}
        className={styles.setMarkImg}
        fallback={<span className={styles.setMarkFallback}>{getInitials(name)}</span>}
      />
    </span>
  );
}

export function RankLogo({ logoUrl, name }) {
  return (
    <span className={styles.rankLogo}>
      <RemoteImg
        src={logoUrl}
        className={styles.rankLogoImg}
        fallback={<span className={styles.rankLogoFallback}>{getInitials(name)}</span>}
      />
    </span>
  );
}

/**
 * A 7-day set value delta. `movement` is null whenever the payload has no
 * comparable snapshot, and the caller renders nothing rather than a zero.
 */
export function ValueDelta({ movement }) {
  if (!movement) return null;

  const toneClass =
    movement.direction === "up"
      ? styles.deltaUp
      : movement.direction === "down"
        ? styles.deltaDown
        : "";
  const glyph = movement.direction === "up" ? "▲" : movement.direction === "down" ? "▼" : "—";
  const percent = formatSignedPercent(movement.percent);
  const amount = typeof movement.amount === "number" ? ` ${signedCurrency0.format(movement.amount)}` : "";
  const label = `${
    movement.direction === "up" ? "Up" : movement.direction === "down" ? "Down" : "Unchanged"
  }${amount} (${percent}) over 7 days`;

  return (
    <span className={`${styles.rankDelta} ${toneClass}`.trim()} title={label}>
      <span className="sr-only">{label}</span>
      <span aria-hidden="true">
        {glyph} {percent} · 7D
      </span>
    </span>
  );
}
