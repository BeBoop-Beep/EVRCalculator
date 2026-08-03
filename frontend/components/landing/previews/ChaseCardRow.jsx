import ChaseCard from "./ChaseCard";
import styles from "../landing.module.css";

/**
 * The chase cards of one set, as a row.
 *
 * This is the page's primary category signal: three real Pokemon cards, large
 * enough to recognize, with their real prices and 7-day direction. It renders
 * nothing at all when the set has no card art — the fallback ladder moves on to
 * the set logo rather than showing an empty frame.
 */
export default function ChaseCardRow({ cards = [], label = "Top chase cards", asOf = null, priority = false }) {
  if (cards.length === 0) return null;

  return (
    <div className={styles.chaseRow}>
      <p className={styles.chaseRowHead}>
        <span>{label}</span>
        {asOf ? <span className={styles.chaseRowAsOf}>{asOf}</span> : null}
      </p>
      <div className={styles.chaseRowCards}>
        {cards.map((card, index) => (
          <ChaseCard key={card.key} card={card} priority={priority && index === 0} />
        ))}
      </div>
    </div>
  );
}
