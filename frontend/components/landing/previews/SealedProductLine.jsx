import { currency0 } from "../landingFormat.mjs";
import styles from "../landing.module.css";

/**
 * The sealed products a set actually sells as, priced.
 *
 * IMAGE-FREE ON PURPOSE. The published sealed contract carries names, families
 * and prices but no artwork, and no sealed imagery exists locally either, so
 * there is nothing truthful to render as a box. Rather than commission a stand-in
 * render, this states the product in type — "Booster Box · $314" — which is
 * still unmistakably sealed Pokemon and is a real published price.
 */
export default function SealedProductLine({ products = [] }) {
  if (products.length === 0) return null;

  return (
    <ul className={styles.sealedList}>
      {products.map((product) => (
        <li key={product.key} className={styles.sealedItem}>
          <span className={styles.sealedIcon} aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none" width="14" height="14">
              <path
                d="M3 6.5 10 3l7 3.5v7L10 17l-7-3.5v-7Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
              />
              <path d="M3 6.5 10 10l7-3.5M10 10v7" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            </svg>
          </span>
          <span className={styles.sealedLabel}>{product.label}</span>
          <span className={styles.sealedPrice}>{currency0.format(product.price)}</span>
        </li>
      ))}
    </ul>
  );
}
