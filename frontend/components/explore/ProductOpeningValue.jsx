"use client";

import { useMemo, useState } from "react";
import styles from "./RipDecisionPage.module.css";
import {
  buildBreakEvenAxis,
  buildEdgeSentence,
  defaultSelectedProductKey,
} from "./ripDecisionContract.mjs";

/**
 * OPENING VALUE — the RIP page's primary decision surface.
 *
 * WHAT THE CHART IS
 * -----------------
 * One shared zero reference: 0% means TODAY'S MARKET PRICE EQUALS MODEL
 * BREAK-EVEN. Each product sits at its own `modelEdgePercent`, which is plain
 * arithmetic on two published numbers (`modelBreakEvenPrice / marketPrice - 1`).
 *
 * WHAT THE CHART IS NOT
 * ---------------------
 * It is NOT a ranking. Placing a bundle and a box on one axis is legitimate
 * because both are measured against their OWN break-even, not against each
 * other. The backend marks cross-format RIP-score comparison unvalidated
 * (`crossFormatComparable: false`), so nothing here sorts products, scores them,
 * numbers them, or names a "best" one. Row order is the contract's order.
 *
 * READABLE WITHOUT COLOUR
 * -----------------------
 * Position, an explicit +/- sign, the written percentage and a stated side
 * ("above"/"below" break-even) all carry the meaning. Colour is a restrained
 * reinforcement, never the only channel.
 */

function money(value) {
  if (value === null || value === undefined) return "—";
  return `$${Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function percent(value, { signed = false } = {}) {
  if (value === null || value === undefined) return "—";
  const rounded = Math.round(Number(value) * 10) / 10;
  const sign = signed && rounded > 0 ? "+" : "";
  return `${sign}${rounded}%`;
}

function ratePercent(value) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

/** Neutral wording for which side of break-even a product sits on. */
function edgeSideLabel(edge) {
  if (edge === null || edge === undefined) return "Model edge unavailable";
  if (edge > 0) return "Above model break-even";
  if (edge < 0) return "Below model break-even";
  return "At model break-even";
}

function BreakEvenRow({ product, axis, selected, onSelect }) {
  const edge = product.modelEdgePercent;
  const position = axis.positionFor(edge);
  const unavailable = position === null;
  // The bar spans from the zero line out to the product's position, so length
  // reads as distance from break-even rather than as an absolute quantity.
  const left = unavailable ? null : Math.min(50, position);
  const width = unavailable ? null : Math.abs(position - 50);

  return (
    <li className={styles.breakEvenRow}>
      <button
        type="button"
        onClick={() => onSelect(product.key)}
        aria-pressed={selected}
        className={styles.breakEvenButton}
        data-selected={selected ? "true" : undefined}
        data-product-key={product.key}
        data-product-family={product.family || undefined}
      >
        <span className={styles.breakEvenLabel}>{product.label}</span>
        <span className={styles.breakEvenTrack} aria-hidden="true">
          <span className={styles.breakEvenZero} />
          {unavailable ? null : (
            <span
              className={styles.breakEvenBar}
              data-direction={edge > 0 ? "above" : edge < 0 ? "below" : "at"}
              style={{ left: `${left}%`, width: `${width}%` }}
            />
          )}
          {unavailable ? null : (
            <span
              className={styles.breakEvenDot}
              data-direction={edge > 0 ? "above" : edge < 0 ? "below" : "at"}
              style={{ left: `${position}%` }}
            />
          )}
        </span>
        <span
          className={styles.breakEvenValue}
          data-direction={edge > 0 ? "above" : edge < 0 ? "below" : "at"}
        >
          {percent(edge, { signed: true })}
        </span>
        {/* The whole meaning of the row, for screen readers and for anyone who
            cannot separate the two directions by colour. */}
        <span className="sr-only">
          {product.label}: {edgeSideLabel(edge)}
          {edge === null ? "" : ` by ${percent(Math.abs(edge))}`}. Market{" "}
          {money(product.marketPrice)}, model break-even{" "}
          {money(product.modelBreakEvenPrice)}.
        </span>
      </button>
    </li>
  );
}

function SelectedProductPanel({ product }) {
  if (!product) return null;

  const edge = product.modelEdgePercent;
  // One sentence of plain arithmetic, so the market-vs-break-even relationship
  // never has to be subtracted by the reader. No recommendation is expressed.
  const sentence = buildEdgeSentence(product);

  const facts = [
    ["Market Price", money(product.marketPrice), "What it costs today"],
    [
      "Model Break-Even",
      money(product.modelBreakEvenPrice),
      "Where modeled value equals price",
    ],
    ["Current Gap", percent(edge, { signed: true }), edgeSideLabel(edge)],
    ["Typical Opening", money(product.typicalOpening), "Median simulated result"],
    [
      "Chance to Recover Cost",
      ratePercent(product.chanceToRecoverCost),
      "Openings that beat their price",
    ],
  ];

  return (
    // Keyed by SKU, not family: several SKUs can share one family.
    <div
      className={styles.selectedProduct}
      data-selected-product={product.key}
      data-product-family={product.family || undefined}
    >
      <div className={styles.selectedProductHead}>
        <p className={styles.eyebrow}>Selected product</p>
        <h3 className={styles.selectedProductTitle}>{product.label}</h3>
        {sentence ? (
          <p className={styles.selectedProductSentence}>{sentence}</p>
        ) : (
          <p className={styles.selectedProductSentence}>
            Current pricing for this product is unavailable, so its position
            against model break-even cannot be shown.
          </p>
        )}
      </div>
      <dl className={styles.economicsGrid}>
        {facts.map(([label, value, helper]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
            <p>{helper}</p>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function ProductOpeningValue({ decision, setName, onSelectProduct }) {
  const products = decision?.products || [];
  const [selectedKey, setSelectedKey] = useState(null);

  const axis = useMemo(() => buildBreakEvenAxis(products), [products]);
  const fallbackKey = useMemo(() => defaultSelectedProductKey(products), [products]);
  const activeKey = selectedKey ?? fallbackKey;
  const selected = products.find((product) => product.key === activeKey) || null;

  function handleSelect(key) {
    setSelectedKey(key);
    if (typeof onSelectProduct === "function") onSelectProduct(key);
  }

  const heading = setName
    ? `Which ${setName} Products Are Worth Opening at Today's Prices?`
    : "Which Products Are Worth Opening at Today's Prices?";

  // THREE different facts, not one. A snapshot that predates the contract, a
  // set with no current run, and a current run that simply models no sealed
  // products are distinct situations, and saying "no current run" for the third
  // is plainly false. None of them falls back to historical rows.
  if (!decision?.available || products.length === 0) {
    const unavailableReason =
      decision?.contractPresent === false
        ? "not-published"
        : decision?.available === false
          ? "no-current-run"
          : "no-modeled-products";
    const unavailableCopy = {
      "not-published":
        "Product opening economics are not published in this set's current snapshot.",
      "no-current-run":
        "No current calculation run is available for this set, so product economics are not shown.",
      "no-modeled-products":
        "No currently modeled sealed products are available for this set.",
    }[unavailableReason];

    return (
      <article
        data-rip-section="opening-value"
        data-opening-value-state={unavailableReason}
        className={`${styles.panel} set-glass-surface`}
      >
        <p className={styles.eyebrow}>Opening value</p>
        <h2 className={styles.sectionTitle}>{heading}</h2>
        <p className={styles.unavailableNote}>{unavailableCopy}</p>
      </article>
    );
  }

  return (
    <article
      data-rip-section="opening-value"
      className={`${styles.panel} set-glass-surface`}
    >
      <p className={styles.eyebrow}>Opening value</p>
      <h2 className={styles.sectionTitle}>{heading}</h2>
      <p className={styles.sectionLede}>
        Each modeled product against its own break-even — the price at which
        modeled long-run opening value equals what you pay. Products are shown in
        pack-count order; they are not ranked against one another.
      </p>

      <div className={styles.breakEvenScale} aria-hidden="true">
        <span>Below model break-even</span>
        <span className={styles.breakEvenScaleZero}>0%</span>
        <span>Above model break-even</span>
      </div>

      <ul className={styles.breakEvenChart}>
        {products.map((product) => (
          <BreakEvenRow
            key={product.key}
            product={product}
            axis={axis}
            selected={product.key === activeKey}
            onSelect={handleSelect}
          />
        ))}
      </ul>

      <SelectedProductPanel product={selected} />
    </article>
  );
}
