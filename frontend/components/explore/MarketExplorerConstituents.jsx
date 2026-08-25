"use client";

import { formatBasketValue } from "@/lib/explore/marketOverviewPresentation.mjs";
import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  CONSTITUENTS_PENDING_PUBLICATION,
  resolveSeriesConstituents,
} from "@/lib/explore/marketExplorerConstituents.mjs";

// Current Constituents — a first-class section, not an incidental query output.
//
// ONE ACTIVE TARGET. Four selected markets do not produce four tables. The user
// names one series and inspects it; a chart with a card market and a sealed
// market alongside each other stays readable because only one composition is on
// screen at a time.
//
// THE TABLE FOLLOWS THE ASSET. Cards show Rank / Card / Set / Rarity / Price;
// sealed products show Rank / Product / Set / Family / Price. The columns come
// from the shared contract rather than from a conditional in here, so the two
// can never half-swap and show a rarity column full of product families.
//
// HONEST BOUNDING. An All-mode market can hold thousands of constituents. The
// table shows the most valuable few and SAYS it is a preview with the true
// total beside it — it never implies it is the complete list.

function cellValue(row, column) {
  const value = row[column.key];
  if (column.price) return formatBasketValue(value);
  if (value === null || value === undefined || value === "") return "—";
  return value;
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
  // Parents are excluded from the picker rather than offered and then refused.
  const inspectable = selectedSeries.filter(
    (series) => series && series.available !== false && series.isParent !== true
  );
  const active = inspectable.find((series) => series.key === activeSeriesId) || null;
  const model = resolveSeriesConstituents(active);

  return (
    <section
      data-market-explorer-constituents
      data-market-constituents-asset={model.asset}
      data-market-constituents-availability={model.availability}
      className="flex min-w-0 flex-col"
      aria-labelledby="market-constituents-heading"
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-3 py-3 sm:px-4">
        <h2 id="market-constituents-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
          Current Constituents
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

          {/* Desktop: the full table, scrolling inside its own container so the
              page itself never scrolls sideways. */}
          <div data-market-constituents-table className="hidden overflow-x-auto px-3 pb-4 sm:px-4 desk:block">
            <table className="w-full min-w-[640px] text-left text-xs">
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
                          column.align === "right" ? "text-right font-semibold" : "",
                          column.numeric || column.price ? "tabular-nums" : "",
                          column.primary ? "font-medium text-[var(--text-primary)]" : "",
                        ].join(" ")}
                      >
                        {column.primary ? (
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

          {/* Mobile: a stacked row per constituent. A five-column table at
              390px is unusable, but Set and price identity are never dropped. */}
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
                    {cellValue(row, model.columns.find((column) => column.primary))}
                  </span>
                  <span className="block truncate text-[10px] text-[var(--text-secondary)]">
                    {row.setName || "—"} · {model.asset === "sealed" ? (row.productFamilyLabel || "—") : (row.rarity || "—")}
                  </span>
                </span>
                <span className="flex-none pt-0.5 text-xs font-semibold tabular-nums text-[var(--text-primary)]">
                  {formatBasketValue(row.marketPrice)}
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
