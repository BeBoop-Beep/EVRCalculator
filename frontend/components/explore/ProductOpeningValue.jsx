"use client";

import { useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
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

/**
 * Money that can legitimately be negative.
 *
 * `money()` above interpolates the sign INSIDE the currency symbol ("$-4.25")
 * because it never had to render a negative. Entertainment Cost does: the
 * backend deliberately does not clamp a product whose modeled contents are
 * worth more than its price, so the minus sign has to survive formatting and
 * has to read as one.
 */
function signedMoney(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  const magnitude = Math.abs(number).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  // Rounding can only ever reach -0.00 from a true negative, and "-$0.00" is a
  // more honest rendering of that than "$0.00".
  return `${number < 0 ? "-" : ""}$${magnitude}`;
}

/** The site's language for a product we do not model. Never a reason string. */
const NOT_MODELED = "Not modeled yet";

/**
 * Explanatory copy for the two published Entertainment Cost figures.
 *
 * Both state the gross-market-value basis explicitly, because the backend's
 * recovery model is `gross_market_value`: expected value carries no deduction
 * for marketplace fees, shipping, grading or spread, which makes the cost shown
 * here a lower bound. Neither describes the figure as a loss, a guaranteed
 * outcome, or a net liquidation value, and the negative case is described as
 * what it is rather than as profit.
 */
export const ENTERTAINMENT_COST_HELP =
  "The product's market price minus the expected market value of the cards you open. Think of it as the amount you're effectively paying for the opening experience. Uses gross market value before selling fees, shipping, spreads, or other transaction costs, and it is a modeled expectation rather than a guaranteed outcome. A negative figure means the model's gross expected market value of the contents is currently above the product's market price.";

export const ENTERTAINMENT_COST_PER_PACK_HELP =
  "Entertainment Cost divided by the number of packs in the product, making different sealed formats easier to compare. Same gross market value basis, so it is a modeled expectation rather than a guaranteed outcome.";

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
  // Supporting economics, deliberately in the ROW rather than only in the
  // selected panel: per-pack is the figure that makes a 36-pack box and a
  // 9-pack ETB directly comparable, and a comparison you have to click through
  // one product at a time is not a comparison.
  const entertainment = product.entertainmentCost;
  const perPack = entertainment?.available ? entertainment.perPack : null;
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
        {/* No colour, no arrow, no judgement: Entertainment Cost is a cost, not
            a verdict, and the existing above/below break-even semantics are the
            page's only evaluative colour system. */}
        <span
          className={styles.breakEvenEntertainment}
          data-entertainment-cost-per-pack={
            perPack === null ? "unavailable" : "available"
          }
          aria-hidden="true"
        >
          {perPack === null ? (
            "—"
          ) : (
            <>
              {signedMoney(perPack)}
              <small> / pack</small>
            </>
          )}
        </span>
        {/* The whole meaning of the row, for screen readers and for anyone who
            cannot separate the two directions by colour. */}
        <span className="sr-only">
          {product.label}: {edgeSideLabel(edge)}
          {edge === null ? "" : ` by ${percent(Math.abs(edge))}`}. Market{" "}
          {money(product.marketPrice)}, model break-even{" "}
          {money(product.modelBreakEvenPrice)}. Entertainment cost{" "}
          {perPack === null
            ? `per pack ${NOT_MODELED.toLowerCase()}`
            : `${signedMoney(perPack)} per pack`}
          .
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

  // Every one of these is read from the contract. Nothing in this panel is
  // arithmetic on two other displayed numbers.
  const entertainment = product.entertainmentCost || {};
  const modeled = entertainment.available === true;

  const facts = [
    // PRIMARY — the existing product decision information, unchanged and first.
    { label: "Market Price", value: money(product.marketPrice), helper: "What it costs today" },
    {
      label: "Model Break-Even",
      value: money(product.modelBreakEvenPrice),
      helper: "Where modeled value equals price",
    },
    { label: "Current Gap", value: percent(edge, { signed: true }), helper: edgeSideLabel(edge) },
    { label: "Typical Opening", value: money(product.typicalOpening), helper: "Median simulated result" },
    {
      label: "Chance to Recover Cost",
      value: ratePercent(product.chanceToRecoverCost),
      helper: "Openings that beat their price",
    },
    // SUPPORTING ECONOMICS — same visual weight as the row above it, placed
    // after the decision metrics so it never competes with RIP scoring.
    //
    // NO SEPARATE "EXPECTED VALUE" TILE. The backend is explicit that
    // `modelBreakEvenPrice` IS the product's expected value expressed as a
    // price, so "Model Break-Even" above already shows it. A second tile would
    // print the identical number under a second name and invite the reader to
    // look for a difference that does not exist.
    {
      label: "Entertainment Cost",
      value: modeled ? signedMoney(entertainment.entertainmentCost) : NOT_MODELED,
      helper: "Price minus modeled value of pulls",
      help: ENTERTAINMENT_COST_HELP,
      modeled,
    },
    {
      label: "Entertainment Cost / Pack",
      value:
        modeled && entertainment.perPack !== null
          ? signedMoney(entertainment.perPack)
          : NOT_MODELED,
      helper: "Normalized so formats compare directly",
      help: ENTERTAINMENT_COST_PER_PACK_HELP,
      modeled: modeled && entertainment.perPack !== null,
    },
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
        {facts.map((fact) => (
          <div
            key={fact.label}
            data-economics-fact={fact.label}
            data-fact-state={
              fact.modeled === false ? "not-modeled" : undefined
            }
          >
            <dt>
              {fact.label}
              {fact.help ? (
                <InfoPopover text={fact.help} />
              ) : null}
            </dt>
            {/* An unmodeled figure is rendered at label weight rather than at
                the 1.35rem number size, so "Not modeled yet" can never be
                skimmed as though it were a measured value. */}
            <dd data-unavailable={fact.modeled === false ? "true" : undefined}>
              {fact.value}
            </dd>
            <p>{fact.helper}</p>
          </div>
        ))}
      </dl>
      {/* Stated, not assumed. The footnote is driven by the published
          `recoveryModel`, so if the backend ever adopts a net basis this line
          stops claiming a gross one. */}
      {entertainment.recoveryModel === "gross_market_value" ? (
        <p className={styles.recoveryNote} data-recovery-model="gross_market_value">
          Entertainment Cost uses gross market value before selling fees,
          shipping, spreads, or other transaction costs, so it is a modeled
          expectation rather than a guaranteed outcome.
        </p>
      ) : null}
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
