"use client";

import { useState } from "react";
import { CARD_THUMBNAIL_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import InfoPopover from "@/components/ui/InfoPopover";
import styles from "./RipDecisionPage.module.css";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value) {
  const parsed = numberOrNull(value);
  return parsed === null ? "Unavailable" : currency.format(parsed);
}

function CardImage({ src, name, compact = false }) {
  const image = optimizedImageUrl(src || null, CARD_THUMBNAIL_WIDTH);
  return (
    <div className={compact ? styles.subjectCardImage : styles.driverImage}>
      {image ? (
        // Existing repository image delivery performs the optimization; this
        // plain image also preserves the compact intrinsic card layout.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} alt={`${name || "Card"} card`} loading="lazy" decoding="async" className="h-full w-full object-contain" />
      ) : <span aria-hidden="true" className="text-xs text-[var(--text-secondary)]">No image</span>}
    </div>
  );
}

export function SimulationDriverCards({ drivers = [], rankings = [], packPaths = {}, normalStateRows = [] }) {
  const [open, setOpen] = useState(false);
  const rows = (Array.isArray(drivers) ? drivers : []).slice(0, 3);
  const rarityRows = (Array.isArray(rankings) ? rankings : [])
    .map((row) => ({ label: row?.rarity_bucket || row?.rarityBucket, value: numberOrNull(row?.total_sampled_value ?? row?.totalSampledValue) }))
    .filter((row) => row.label && row.value !== null)
    .sort((a, b) => b.value - a.value);
  const maxRarity = Math.max(0, ...rarityRows.map((row) => row.value));
  const pathRows = Object.entries(packPaths && typeof packPaths === "object" ? packPaths : {}).filter(([, value]) => numberOrNull(value) !== null);

  return (
    <>
      {rows.length ? (
        <div data-simulation-driver-cards className="mt-4 grid gap-3 md:grid-cols-3">
          {rows.map((driver, index) => {
            const name = driver.card_name || "Card name unavailable";
            return (
              <article key={driver.canonical_card_id || driver.id || `${name}:${index}`} className={styles.driverCard}>
                <CardImage src={driver.image_url || driver.image_small_url || driver.image_large_url} name={name} />
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-[var(--text-primary)]">{name}</h3>
                  <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div><dt className="text-[var(--text-secondary)]">Market price</dt><dd className="mt-0.5 font-semibold tabular-nums text-[var(--text-primary)]">{money(driver.current_near_mint_price)}</dd></div>
                    <div><dt className="text-[var(--text-secondary)]">EV contribution</dt><dd className="mt-0.5 font-semibold tabular-nums text-[var(--text-primary)]">{money(driver.ev_contribution)}</dd></div>
                  </dl>
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">Major contributor to modeled pack value.</p>
                </div>
              </article>
            );
          })}
        </div>
      ) : <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">Simulation driver cards are not available for this set yet.</p>}

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
        <button type="button" aria-expanded={open} aria-controls="rip-more-simulation-detail" onClick={() => setOpen((value) => !value)} className={styles.disclosureButton}>
          <span>View value structure details</span><span aria-hidden="true">{open ? "−" : "+"}</span>
        </button>
        {open ? (
          <div id="rip-more-simulation-detail" className="mt-4 grid gap-5 lg:grid-cols-2">
            <section>
              <h3 className="font-semibold text-[var(--text-primary)]">Value Contribution by Rarity</h3>
              {rarityRows.length ? <div className="mt-3 space-y-3">{rarityRows.map((row) => <div key={row.label}><div className="flex justify-between gap-3 text-sm"><span className="text-[var(--text-secondary)]">{String(row.label).replaceAll("_", " ")}</span><span className="font-semibold tabular-nums text-[var(--text-primary)]">{money(row.value)}</span></div><div className={styles.detailRail}><span style={{ width: `${maxRarity > 0 ? (row.value / maxRarity) * 100 : 0}%` }} /></div></div>)}</div> : <p className="mt-2 text-sm text-[var(--text-secondary)]">Rarity contribution is unavailable.</p>}
            </section>
            <section>
              <h3 className="font-semibold text-[var(--text-primary)]">Pack Breakdown</h3>
              {pathRows.length || normalStateRows.length ? <dl className="mt-3 space-y-2">{pathRows.slice(0, 4).map(([label, value]) => <div key={label} className="flex justify-between gap-3 text-sm"><dt className="capitalize text-[var(--text-secondary)]">{label.replaceAll("_", " ")}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">{Number(value).toLocaleString()}</dd></div>)}{normalStateRows.slice(0, 4).map(([label, value]) => <div key={`state:${label}`} className="flex justify-between gap-3 text-sm"><dt className="capitalize text-[var(--text-secondary)]">{String(label).replaceAll("_", " ")}</dt><dd className="font-semibold tabular-nums text-[var(--text-primary)]">{Number(value).toLocaleString()}</dd></div>)}</dl> : <p className="mt-2 text-sm text-[var(--text-secondary)]">Pack breakdown is unavailable.</p>}
            </section>
          </div>
        ) : null}
      </div>
    </>
  );
}

function SubjectPath({ label, path }) {
  if (!path) return null;
  return (
    <div className={styles.subjectPath}>
      <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</p>
      <div className="mt-2 flex min-w-0 items-center gap-3">
        <CardImage src={path.imageUrl} name={path.cardName} compact />
        <div className="min-w-0"><p className="line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">{path.cardName || "Card name unavailable"}</p><p className="mt-1 text-xs text-[var(--text-secondary)]">{path.impliedOdds ? `Approx. 1 in ${Math.round(path.impliedOdds).toLocaleString()} packs` : "Modeled odds unavailable"}</p></div>
      </div>
    </div>
  );
}

export function CollectorDriverSubjects({ subjects = [] }) {
  if (!subjects.length) return <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">Top collector subjects are not available for this set yet.</p>;
  return <div data-collector-driver-subjects className="mt-4 grid gap-3 xl:grid-cols-3">{subjects.map((subject) => <article key={subject.subjectName} className={styles.subjectCard}><div className="flex items-start justify-between gap-3"><h3 className="text-lg font-semibold text-[var(--text-primary)]">{subject.subjectName}</h3>{subject.demandShareLabel ? <div className="text-right"><p data-demand-share-value className="text-xl font-semibold leading-none tabular-nums text-[var(--text-primary)]">{subject.demandShareLabel}</p><p data-demand-share-label className="mt-1 flex items-center justify-end gap-1 text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--text-secondary)]">Share of set demand <InfoPopover text="Estimates how much of this set's modeled Pokémon-subject demand is associated with this Pokémon. It is not pull probability, market value, or Collector Appeal points." /></p></div> : null}</div><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2"><SubjectPath label="More attainable" path={subject.accessiblePath} /><SubjectPath label="Elite chase" path={subject.elitePath} /></div></article>)}</div>;
}
