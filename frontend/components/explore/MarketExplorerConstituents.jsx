"use client";

import { useState } from "react";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { formatBasketValue } from "@/lib/explore/marketOverviewPresentation.mjs";
import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  CONSTITUENTS_PENDING_PUBLICATION,
  CONSTITUENT_MOVEMENT_WINDOWS,
  DEFAULT_CONSTITUENT_MOVEMENT_WINDOW,
  getConstituentChange,
  isEnumerableSeries,
  resolveSeriesConstituents,
} from "@/lib/explore/marketExplorerConstituents.mjs";

// Current Constituents — a first-class section, not an incidental query output.
//
// IT ANSWERS TWO QUESTIONS. "What is inside this market" was the original job.
// "How are those things moving" is the second, and it is why every row carries
// its OWN change rather than the market's aggregate return — an aggregate
// repeated down the column would look like data and tell the reader nothing.
//
// ONE MOVEMENT COLUMN, NOT FOUR. 1D / 7D / 30D / 3M as four simultaneous
// columns makes a six-column table into a nine-column one that overflows at
// every width. The window is a local control in this section's header and the
// column follows it; the header label always names the window being shown.
//
// ONE ACTIVE TARGET. Four selected markets do not produce four tables. The user
// names one series and inspects it; a chart with a card market and a sealed
// market alongside each other stays readable because only one composition is on
// screen at a time.
//
// THE TABLE FOLLOWS THE ASSET. Cards show Rank / Card / Set / Rarity / Price /
// Change; sealed products show Rank / Product / Set / Family / Price / Change.
// The columns come from the shared contract rather than from a conditional in
// here, so the two can never half-swap and show a rarity column full of product
// families.
//
// MOVEMENT COLOR IS PERFORMANCE, NOT IDENTITY. Green up, red down, neutral
// flat — the same vocabulary the rest of the product uses for returns. It is
// deliberately unrelated to the market's series color, which appears only in
// the picker chips as identity.
//
// HONEST BOUNDING. An All-mode market can hold thousands of constituents. The
// table shows the most valuable few and SAYS it is a preview with the true
// total beside it — it never implies it is the complete list.

function toneOf(percent) {
  if (percent > 0) return POSITIVE_VALUE_COLOR;
  if (percent < 0) return NEGATIVE_VALUE_COLOR;
  return "var(--text-secondary)";
}

/**
 * One row's movement, or an em dash.
 *
 * A dash means "no comparable observation at this window's start" — a
 * constituent that entered the market nine days ago genuinely has no 30D
 * movement. Printing 0.00% there would claim the price held steady, which is a
 * different and false statement.
 */
function ChangeCell({ row, window, label }) {
  const percent = getConstituentChange(row, window);
  if (percent === null) {
    return (
      <span data-market-constituent-change-unavailable className="tabular-nums text-[var(--text-secondary)]">
        <span aria-hidden="true">—</span>
        <span className="sr-only">{`No ${window} movement: not enough history`}</span>
      </span>
    );
  }
  const glyph = percent > 0 ? "▲" : percent < 0 ? "▼" : "—";
  return (
    <span
      data-market-constituent-change={window}
      className="inline-flex items-baseline gap-1 tabular-nums"
      style={{ color: toneOf(percent) }}
    >
      <span aria-hidden="true" className="text-[0.75em] leading-none">{glyph}</span>
      <span aria-hidden="true">{`${percent > 0 ? "+" : ""}${percent.toFixed(2)}%`}</span>
      <span className="sr-only">{`${label}: ${percent.toFixed(2)} percent over ${window}`}</span>
    </span>
  );
}

function cellValue(row, column) {
  const value = row[column.key];
  if (column.price) return formatBasketValue(value);
  if (value === null || value === undefined || value === "") return "—";
  return value;
}

/**
 * The local movement window control.
 *
 * Deliberately scoped to this section: it changes which movement column the
 * table shows and NOTHING else. The chart above keeps its own timeframe, which
 * is a cross-market comparison window and a different question.
 */
function MovementWindowSelector({ value, onChange }) {
  return (
    <div
      data-market-constituents-window-selector
      role="group"
      aria-label="Constituent movement window"
      className="flex flex-none items-center gap-0.5 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]/40 p-0.5"
    >
      {CONSTITUENT_MOVEMENT_WINDOWS.map((window) => {
        const isActive = window === value;
        return (
          <button
            key={window}
            type="button"
            data-market-constituents-window={window}
            data-market-constituents-window-active={isActive ? "true" : "false"}
            aria-pressed={isActive}
            onClick={() => onChange(window)}
            className={[
              "min-h-9 rounded px-2 text-[10px] font-semibold tabular-nums transition-colors desk:min-h-0 desk:py-1",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
              isActive
                ? "bg-[rgba(45,212,191,0.14)] text-[rgb(45,212,191)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            {window}
          </button>
        );
      })}
    </div>
  );
}

function SeriesPicker({ series, activeId, onSelect }) {
  if (series.length <= 1) return null;
  return (
    <div data-market-constituents-picker className="flex flex-wrap gap-1.5 px-3 pb-2 sm:px-4">
      {series.map((entry) => {
        const isActive = entry.key === activeId;
        return (
          <button
            key={entry.key}
            type="button"
            data-market-constituents-target={entry.key}
            aria-pressed={isActive}
            onClick={() => onSelect?.(entry.key)}
            className={[
              "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors desk:min-h-0 desk:py-1",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]",
              isActive
                ? "border-[rgb(45,212,191)] bg-[rgba(45,212,191,0.12)] text-[rgb(45,212,191)]"
                : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span aria-hidden="true" className="inline-block h-2 w-2 flex-none rounded-[2px]" style={{ backgroundColor: entry.color }} />
            <span className="max-w-[14rem] truncate">{entry.shortLabel || entry.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function MarketExplorerConstituents({
  selectedSeries = [],
  activeSeriesId = null,
  onSelectSeries,
}) {
  // Local, unpersisted: which window you are reading is a posture, not
  // research, and it does not belong in the URL beside the chart's timeframe.
  const [movementWindow, setMovementWindow] = useState(DEFAULT_CONSTITUENT_MOVEMENT_WINDOW);

  // ENUMERABILITY, NOT PARENTHOOD, decides what can be inspected — the same
  // rule `resolveActiveDetailSeriesId` uses, so the picker and the detail
  // target cannot disagree.
  //
  // This used to filter on `isParent !== true`, which silently disagreed with
  // the resolver: Total Sealed IS a parent and DOES publish its roster, and it
  // is the only surface anywhere that lists the ten residual `otherSealed`
  // products. The resolver would happily target it, the picker would drop it,
  // and the panel then reported "not applicable" for a market whose
  // composition was sitting in the payload.
  const inspectable = selectedSeries.filter(
    (series) => series && series.available !== false && isEnumerableSeries(series)
  );
  const active = inspectable.find((series) => series.key === activeSeriesId) || null;
  const model = resolveSeriesConstituents(active, { movementWindow });
  const primaryColumn = model.columns.find((column) => column.primary);

  return (
    <section
      data-market-explorer-constituents
      data-market-constituents-asset={model.asset}
      data-market-constituents-availability={model.availability}
      data-market-constituents-movement-window={model.movementWindow}
      data-market-constituents-has-movement={model.hasMovement ? "true" : "false"}
      className="flex min-w-0 flex-col"
      aria-labelledby="market-constituents-heading"
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-3 py-3 sm:px-4">
        <h2 id="market-constituents-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
          Constituents
        </h2>
        {active ? (
          <span data-market-constituents-active className="text-[11px] text-[var(--text-secondary)]">
            {active.label}
            {model.availability === CONSTITUENTS_AVAILABLE ? (
              <>
                {" · "}
                <span data-market-constituents-count className="tabular-nums">{model.totalCount}</span>
                {" "}
                {model.asset === "sealed" ? "products" : "cards"}
                {model.bounded ? ` · showing top ${model.rows.length} by price` : ""}
                {model.asOf ? ` · as of ${model.asOf}` : ""}
              </>
            ) : null}
          </span>
        ) : (
          <span className="text-[11px] text-[var(--text-secondary)]">
            Select a market to see what is inside it.
          </span>
        )}
        {model.availability === CONSTITUENTS_AVAILABLE ? (
          <div className="ml-auto">
            <MovementWindowSelector value={model.movementWindow} onChange={setMovementWindow} />
          </div>
        ) : null}
      </div>

      <SeriesPicker series={inspectable} activeId={active?.key || null} onSelect={onSelectSeries} />

      {model.availability === CONSTITUENTS_AVAILABLE ? (
        <>
          {model.belowRequestedTopN ? (
            <p data-market-constituents-short className="px-3 pb-2 text-[10px] text-[var(--text-secondary)] sm:px-4">
              This filtered market holds {model.totalCount} eligible constituents, fewer than the
              requested Top {model.requestedTopN}. The basket is reported at its real size rather than padded.
            </p>
          ) : null}

          {/* Said once, at the top, rather than as a dash-shaped mystery in
              every row: a snapshot published before the movement contract
              carries no per-constituent change at all. */}
          {model.hasMovement === false ? (
            <p data-market-constituents-movement-pending className="px-3 pb-2 text-[10px] text-[var(--text-secondary)] sm:px-4">
              Per-constituent movement will be available for this market after the next market publication.
            </p>
          ) : null}

          {/* Desktop: the full table, scrolling inside its own container so the
              page itself never scrolls sideways. */}
          <div data-market-constituents-table className="hidden overflow-x-auto px-3 pb-4 sm:px-4 desk:block">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="border-y border-[var(--border-subtle)] text-[10px] uppercase tracking-[0.07em] text-[var(--text-secondary)]">
                <tr>
                  {model.columns.map((column) => (
                    <th key={column.key} scope="col" className={`px-3 py-2 ${column.align === "right" ? "text-right" : ""}`}>
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {model.rows.map((row) => (
                  <tr
                    key={row[model.idField]}
                    data-market-constituent={row[model.idField]}
                    className="border-b border-[var(--border-subtle)] last:border-0"
                  >
                    {model.columns.map((column) => (
                      <td
                        key={column.key}
                        className={[
                          "px-3 py-2",
                          column.align === "right" ? "text-right" : "",
                          column.align === "right" && !column.change ? "font-semibold" : "",
                          column.change ? "font-semibold" : "",
                          column.numeric || column.price ? "tabular-nums" : "",
                          column.primary ? "font-medium text-[var(--text-primary)]" : "",
                        ].join(" ")}
                      >
                        {column.change ? (
                          <ChangeCell
                            row={row}
                            window={column.window}
                            label={cellValue(row, primaryColumn)}
                          />
                        ) : column.primary ? (
                          <span className="flex items-center gap-2">
                            {row.imageUrl ? (
                              <img src={row.imageUrl} alt="" loading="lazy" className="h-10 w-7 flex-none rounded object-cover" />
                            ) : null}
                            <span className="min-w-0 truncate">{cellValue(row, column)}</span>
                          </span>
                        ) : cellValue(row, column)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: a stacked row per constituent. A six-column table at 390px
              is unusable, but Set, price and movement are never dropped —
              movement sits under the price where the eye already is. */}
          <ul data-market-constituents-cards className="space-y-1.5 px-3 pb-4 sm:px-4 desk:hidden">
            {model.rows.map((row) => (
              <li
                key={row[model.idField]}
                data-market-constituent={row[model.idField]}
                className="flex items-start gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/30 px-2.5 py-2"
              >
                <span className="w-5 flex-none pt-0.5 text-[10px] tabular-nums text-[var(--text-secondary)]">{row.rank}</span>
                {row.imageUrl ? (
                  <img src={row.imageUrl} alt="" loading="lazy" className="h-12 w-9 flex-none rounded object-cover" />
                ) : null}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-[var(--text-primary)]">
                    {cellValue(row, primaryColumn)}
                  </span>
                  <span className="block truncate text-[10px] text-[var(--text-secondary)]">
                    {row.setName || "—"} · {model.asset === "sealed" ? (row.productFamilyLabel || "—") : (row.rarity || "—")}
                  </span>
                </span>
                <span className="flex flex-none flex-col items-end pt-0.5">
                  <span className="text-xs font-semibold tabular-nums text-[var(--text-primary)]">
                    {formatBasketValue(row.marketPrice)}
                  </span>
                  <span className="mt-0.5 text-[10px] font-semibold">
                    <ChangeCell
                      row={row}
                      window={model.movementWindow}
                      label={cellValue(row, primaryColumn)}
                    />
                    <span aria-hidden="true" className="ml-1 font-normal text-[var(--text-secondary)]">{model.movementWindow}</span>
                  </span>
                </span>
              </li>
            ))}
          </ul>

          {model.bounded ? (
            <p data-market-constituents-bounded className="px-3 pb-4 text-[10px] leading-relaxed text-[var(--text-secondary)] sm:px-4">
              Showing the {model.rows.length} most valuable of {model.totalCount}. This is a preview of the
              market&apos;s composition, not the complete list.
            </p>
          ) : null}
        </>
      ) : (
        <p
          role="status"
          data-market-constituents-unavailable={model.availability}
          className="px-3 pb-6 pt-1 text-xs text-[var(--text-secondary)] sm:px-4"
        >
          {model.availability === CONSTITUENTS_PENDING_PUBLICATION
            ? model.reason
            : (model.reason || "Select a market to see what is inside it.")}
        </p>
      )}
    </section>
  );
}

export { CONSTITUENTS_AVAILABLE, CONSTITUENTS_NOT_APPLICABLE, CONSTITUENTS_PENDING_PUBLICATION };
