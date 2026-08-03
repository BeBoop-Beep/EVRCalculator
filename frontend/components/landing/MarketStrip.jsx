import Link from "next/link";

import { currency0, formatSignedPercent } from "./landingFormat.mjs";
import RemoteImg from "./previews/RemoteImg";
import { RankLogo } from "./previews/previewPrimitives";
import styles from "./landing.module.css";

/**
 * The live market strip, replacing the decorative "Also ranked" pills.
 *
 * Three published signals answering three different questions — which set opens
 * best, which set is worth most, which card moved hardest — each one a real set
 * or card with a real number. A signal whose data is missing is omitted by the
 * selector rather than padded, so the strip can render one, two or three items.
 * It is a wrapping grid at every width: no carousel, nothing auto-advancing,
 * nothing hidden behind a swipe.
 */
function Movement({ movement }) {
  if (!movement || movement.percent === null || movement.percent === undefined) return null;

  const toneClass =
    movement.direction === "up" ? styles.deltaUp : movement.direction === "down" ? styles.deltaDown : "";
  const glyph = movement.direction === "up" ? "▲" : movement.direction === "down" ? "▼" : "—";
  const percent = formatSignedPercent(movement.percent);

  return (
    <span className={`${styles.stripMove} ${toneClass}`.trim()}>
      <span className="sr-only">{`${percent} over 7 days`}</span>
      <span aria-hidden="true">
        {glyph} {percent} · 7D
      </span>
    </span>
  );
}

export default function MarketStrip({ signals = [] }) {
  if (signals.length === 0) return null;

  return (
    <section className={styles.strip} aria-labelledby="landing-market-strip-heading">
      <div className={styles.shell}>
        <h2 id="landing-market-strip-heading" className={styles.stripHeading}>
          <span className={styles.liveDot} aria-hidden="true" />
          Live Pokémon market
        </h2>

        <ul className={styles.stripList}>
          {signals.map((signal) => (
            <li key={signal.key}>
              <Link href={signal.href} className={styles.stripItem}>
                <span className={styles.stripThumb}>
                  {signal.cardImage ? (
                    /* Card art where the signal is about a card; a dead URL
                       falls back to the set logo, and that to initials. */
                    <RemoteImg
                      src={signal.cardImage}
                      className={styles.stripCardImg}
                      width={245}
                      height={342}
                      fallback={<RankLogo logoUrl={signal.logoUrl} name={signal.setName} />}
                    />
                  ) : (
                    <RankLogo logoUrl={signal.logoUrl} name={signal.setName} />
                  )}
                </span>

                <span className={styles.stripBody}>
                  <span className={styles.stripLabel}>{signal.label}</span>
                  <span className={styles.stripName}>{signal.cardName || signal.setName}</span>
                  {signal.cardName && signal.setName ? (
                    <span className={styles.stripSub}>{signal.setName}</span>
                  ) : null}
                </span>

                <span className={styles.stripTrail}>
                  <span className={styles.stripValue}>
                    {typeof signal.value === "number" ? currency0.format(signal.value) : signal.value}
                  </span>
                  <span className={styles.stripUnit}>{signal.unit}</span>
                  <Movement movement={signal.movement} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
