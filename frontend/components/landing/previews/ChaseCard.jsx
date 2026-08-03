import RemoteImg from "./RemoteImg";
import styles from "../landing.module.css";

/**
 * One real Pokemon card, at a size where you can tell it is a Pokemon card.
 *
 * The frame reserves the card's aspect ratio (245x342, the pokemontcg.io art
 * box) BEFORE the image arrives, so a slow card image never reflows the row
 * around it. A failed load falls back to a typed nameplate rather than a broken
 * image icon — the same onError pattern Explore's ladder logos use, and the
 * reason this one small piece of the page is a client component.
 */
export default function ChaseCard({ card, priority = false }) {
  return (
    <figure className={styles.chaseCard}>
      <span className={styles.chaseCardFrame}>
        <RemoteImg
          src={card.image}
          alt={`${card.name} card`}
          className={styles.chaseCardImg}
          width={245}
          height={342}
          loading={priority ? "eager" : "lazy"}
          fallback={
            <span className={styles.chaseCardFallback}>
              <span className={styles.chaseCardFallbackName}>{card.name}</span>
              {card.number ? <span className={styles.chaseCardFallbackMeta}>{card.number}</span> : null}
            </span>
          }
        />
      </span>
      <figcaption className={styles.chaseCardMeta}>
        <span className={styles.chaseCardName}>{card.name}</span>
        {card.price !== null ? (
          <span className={styles.chaseCardPrice}>
            ${card.price.toFixed(0)}
            {card.direction && card.direction !== "flat" ? (
              <span
                className={card.direction === "up" ? styles.deltaUp : styles.deltaDown}
                aria-label={`${card.direction === "up" ? "Up" : "Down"} ${Math.abs(card.changePercent).toFixed(1)} percent over 7 days`}
              >
                {card.direction === "up" ? "▲" : "▼"}
              </span>
            ) : null}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}
