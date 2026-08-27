"use client";

import { useMemo } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import {
  formatEvRepPacks,
  formatEvRepPercent,
  selectEvRepresentativenessPublicV1,
} from "../evRepresentativenessSelector.mjs";
import styles from "../RipDecisionPage.module.css";

export default function EvRepresentativenessSection({
  evRepresentativeness = null,
  calculationRunId = null,
  headingId,
  products = [],
}) {
  const evRep = useMemo(
    () =>
      selectEvRepresentativenessPublicV1(
        evRepresentativeness,
        calculationRunId,
      ),
    [evRepresentativeness, calculationRunId],
  );
  if (!evRep) return null;

  const productCandidates = (Array.isArray(products) ? products : [])
    .map((product) => ({
      product,
      row: evRep.realizationByPackCount?.find(
        (item) => item.packCount === Number(product?.packCount),
      ),
    }))
    .filter((item) => item.row)
    .sort(
      (a, b) =>
        Number(/booster box/i.test(b.product?.productName || "")) -
        Number(/booster box/i.test(a.product?.productName || "")),
    );
  const realistic = productCandidates[0] || null;

  return (
    <section className={styles.evRepSection} aria-labelledby={headingId}>
      <header>
        <div>
          <h3 id={headingId}>When Does EV Start Looking Real?</h3>
          <p>
            Expected Value is a long-run average. This analysis measures how
            often real-sized opening runs get close to it.
          </p>
        </div>
        <InfoPopover text="Estimated from one million modeled outcomes. Horizons assume independent pack draws and are not opening recommendations." />
      </header>
      <div className={styles.evMilestones}>
        {realistic ? (
          <div>
            <span>
              {realistic.product.productName} —{" "}
              {realistic.row.packCount.toLocaleString("en-US")} packs
            </span>
            <strong>
              {formatEvRepPercent(realistic.row.probabilityAtLeast80PercentEv)}
            </strong>
            <small>
              of modeled {realistic.row.packCount.toLocaleString("en-US")}-pack
              runs averaged at least 80% of long-run EV
            </small>
          </div>
        ) : null}
        <div>
          <span>Reach 80% of EV Reliably</span>
          <strong>
            {evRep.realizationHorizon
              ? formatEvRepPacks(evRep.realizationHorizon.packCount)
              : "Not confirmed"}
          </strong>
          <small>
            The first modeled pack count where 80% of runs average at least 80%
            of long-run EV · One-sided threshold
          </small>
        </div>
        <div>
          <span>Converge Near EV</span>
          <strong>
            {evRep.convergenceHorizon
              ? formatEvRepPacks(evRep.convergenceHorizon.packCount)
              : "Not confirmed"}
          </strong>
          <small>
            The first modeled pack count where 80% of runs average within ±20%
            of long-run EV · Two-sided convergence
          </small>
        </div>
      </div>
      {evRep.realizationByPackCount.length ? (
        <details className={styles.evRepRealization}>
          <summary>Chance to Reach at Least 80% of EV</summary>
          <div
            role="table"
            aria-label="Chance to reach at least 80% of EV by pack count"
          >
            {evRep.realizationByPackCount.map((row) => (
              <div
                role="row"
                key={row.packCount}
                className={styles.evRepTableRow}
              >
                <span role="cell">
                  {row.packCount.toLocaleString("en-US")} packs
                </span>
                <strong role="cell">
                  {formatEvRepPercent(row.probabilityAtLeast80PercentEv)}
                </strong>
              </div>
            ))}
          </div>
          <p>
            Each percentage is the share of modeled runs at that pack count
            whose average return reached at least 80% of long-run Expected
            Value.
          </p>
        </details>
      ) : null}
    </section>
  );
}
