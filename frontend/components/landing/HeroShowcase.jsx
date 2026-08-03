import ChaseCardRow from "./previews/ChaseCardRow";
import FeaturedSetPanel from "./previews/FeaturedSetPanel";
import SealedProductLine from "./previews/SealedProductLine";
import { SetMark } from "./previews/previewPrimitives";
import { formatAsOf } from "./landingFormat.mjs";
import styles from "./landing.module.css";

/**
 * The hero's product side: what inDex is looking at, shown rather than named.
 *
 * FALLBACK LADDER, in the order the brief sets out:
 *   1. a sealed-product image        - unavailable: the published sealed
 *      contract carries names, families and prices but no artwork, and no
 *      sealed imagery exists locally, so nothing is invented to fill the slot
 *   2. another product image         - unavailable for the same reason
 *   3. set logo + top chase cards    - what renders, from real card art
 *   4. the intelligence panel alone  - when a set has no published card art
 *
 * Real sealed products still appear, priced, as typed lines: that is truthful
 * sealed Pokemon content without a stand-in render.
 */
export default function HeroShowcase({ set, chaseCards = [], sealedProducts = [], cardsAsOf = null }) {
  const asOf = formatAsOf(cardsAsOf);

  return (
    <div className={styles.showcase}>
      {set ? (
        <div className={styles.showcaseHead}>
          <SetMark logoUrl={set.logoUrl || set.symbolUrl} name={set.name} className={styles.showcaseLogo} />
          <span className={styles.setText}>
            <span className={styles.showcaseSetName}>{set.name}</span>
            <span className={styles.showcaseSetMeta}>
              {set.era ? `${set.era} · ` : ""}Featured set
            </span>
          </span>
        </div>
      ) : null}

      <ChaseCardRow cards={chaseCards} label="Top chase cards" asOf={asOf} priority />

      <SealedProductLine products={sealedProducts} />

      <FeaturedSetPanel set={set} marketDate={cardsAsOf} />
    </div>
  );
}
