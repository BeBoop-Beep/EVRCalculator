import Link from "next/link";

import WaitlistCta from "./WaitlistCta";
import styles from "./landing.module.css";

/**
 * Section 6 — today's product first, the future one named honestly.
 *
 * Explore is what ships, so it takes the yellow. The portfolio waitlist sits
 * beside it and is described as something inDex is expanding into, never as a
 * capability a visitor can use now.
 */
export default function FinalCtaSection() {
  return (
    <section className={styles.section} aria-labelledby="landing-final-heading">
      <div className={styles.shell}>
        <div className={styles.final}>
          <h2 id="landing-final-heading" className={styles.finalTitle}>
            Market intelligence for every collecting decision.
          </h2>
          <p className={styles.finalLede}>
            Explore Pokémon sets today and build a more informed collectible portfolio as inDex
            expands.
          </p>
          <div className={styles.finalActions}>
            <Link href="/Explore" className={styles.finalPrimary}>
              Explore Pokémon sets
            </Link>
            <WaitlistCta
              source="landing_page_final"
              label="Join the portfolio waitlist"
              variant="link"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
