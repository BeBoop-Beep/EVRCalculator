"use client";

import { useEffect, useRef, useState } from "react";
import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";
import { formatBasketValue } from "@/lib/explore/marketOverviewPresentation.mjs";
import {
  CONSTITUENTS_AVAILABLE,
  CONSTITUENTS_NOT_APPLICABLE,
  CONSTITUENTS_PENDING_PUBLICATION,
  CONSTITUENT_MOVEMENT_WINDOWS,
  constituentMovementWindowLabel,
  DEFAULT_CONSTITUENT_MOVEMENT_WINDOW,
  hasAnyConstituentMovement,
  buildConstituentColumns,
  getConstituentChange,
  isEnumerableSeries,
  resolveSeriesAsset,
  resolveSeriesConstituents,
  resolveVariantLabel,
} from "@/lib/explore/marketExplorerConstituents.mjs";
import ConstituentThumbnail from "./MarketExplorerConstituentPreview";
import { buildConstituentSwitcherEntries } from "@/lib/explore/marketExplorerWorkspace.mjs";
import { resolveCompositionCapability } from "@/lib/explore/marketExplorerComposition.mjs";
import useMarketExplorerConstituentPage from "@/hooks/explore/useMarketExplorerConstituentPage";
import { CONSTITUENT_ERROR } from "@/lib/explore/marketExplorerConstituentPaging.mjs";

const PREVIEW_ROWS = 5;
// Truthful, specific copy for every prepared-roster state. "Next publication"
// is deliberately NOT used here: it is only ever said for a legacy snapshot
// series that explicitly reports publication-pending.
const PREPARED_STATE_COPY = {
  unavailable: "Composition is not published for this market.",
  notApplicable: "This market has no enumerable constituent roster.",
  empty: "This market currently has no constituents.",
};
const PREPARED_ERROR_COPY = {
  [CONSTITUENT_ERROR.auth]: "Sign in to view this market's constituents.",
  [CONSTITUENT_ERROR.entitlement]: "Constituents are included with Index+.",
  [CONSTITUENT_ERROR.generationMismatch]: "Prepared data was updated. Refreshing constituents\u2026",
  default: "Constituents temporarily unavailable.",
};
const NON_RETRYABLE = new Set([CONSTITUENT_ERROR.auth, CONSTITUENT_ERROR.entitlement]);

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
 * A card's variant identity (First Edition / Unlimited / Shadowless /
 * Reverse Holo / Holo / Non-Holo), rendered only when the row actually
 * carries one — see resolveVariantLabel for exactly when that is. Sealed
 * products have no such concept and never pass a row here.
 */
function VariantBadge({ row }) {
  const label = resolveVariantLabel(row);
  if (!label) return null;
  return (
    <span
      data-market-constituent-variant
      className="ml-1.5 inline-flex flex-none items-center rounded border border-[var(--border-subtle)] px-1 py-0.5 text-[9px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]"
    >
      {label}
    </span>
  );
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
            {constituentMovementWindowLabel(window)}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The constituent SWITCHER. Lists every ACTIVE market so the user can change what
 * the panel inspects without closing it. Clicking a chip changes ONLY the
 * constituent target: it never removes a market, toggles chart visibility,
 * changes focus, or triggers the Builder. A chart-hidden market stays
 * selectable; a market that cannot be enumerated renders disabled/unavailable
 * (marked by data-market-constituents-target-unavailable) instead of pretending
 * to load. The current target has the strongest (violet) state.
 */
function ConstituentSwitcher({ entries, onSelect }) {
  if (entries.length <= 1) return null;
  return (
    <div data-market-constituents-picker role="group" aria-label="Constituent market" className="flex flex-wrap gap-1.5 px-3 pb-2 sm:px-4">
      {entries.map((entry) => {
        const stateProps = entry.disabled
          ? { "data-market-constituents-target-unavailable": entry.key, disabled: true, "aria-disabled": true, title: "This market has no enumerable constituent roster" }
          : { "data-market-constituents-target": entry.key, "aria-pressed": entry.isTarget, onClick: () => onSelect?.(entry.key) };
        return (
          <button
            key={entry.key}
            type="button"
            {...stateProps}
            data-market-constituents-target-hidden={entry.isHidden ? "true" : undefined}
            className={[
              "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors desk:min-h-0 desk:py-1",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/80",
              entry.disabled
                ? "cursor-not-allowed border-dashed border-[var(--border-subtle)] text-[var(--text-secondary)] opacity-45"
                : entry.isTarget
                  ? "border-violet-300 bg-violet-500/[.22] font-semibold text-violet-100 shadow-[inset_0_0_0_1px_rgba(196,181,253,.25)]"
                  : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-violet-400/50 hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            <span aria-hidden="true" className="inline-block h-2 w-2 flex-none rounded-[2px]" style={{ backgroundColor: entry.color }} />
            <span className="max-w-[14rem] truncate">{entry.label}</span>
            {entry.isHidden ? <span className="text-[9px] font-normal text-[var(--text-secondary)]">(hidden on chart)</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/**
 * A QUERY-BUILT market's constituents, loaded a backend page at a time.
 *
 * WHY THIS EXISTS SEPARATELY. `resolveSeriesConstituents` reads whatever rows
 * already arrived on the series object — correct for a prepared/parent
 * market, whose published roster is small by construction, but wrong for a
 * custom query: the market-summary response never carries a query market's
 * composition at all (`responseMode: "summary"` — see
 * useMarketExplorerQueries), and even if it did, Global All Raw alone is
 * 33,955 rows. This component owns its OWN loading/error state
 * (`useMarketExplorerConstituentPage`), independent of the chart's, so a slow
 * or failed constituent page never blocks the rest of the workspace.
 */
function QueryConstituentSection({ series, identity, movementWindow, mode = "expanded", prepared = false, onRefreshPrepared, pageCache = null }) {
  const asset = resolveSeriesAsset(series);
  const idField = asset === "sealed" ? "sealedProductId" : "canonicalCardId";
  // Query rows represent physical instruments. Legitimate card variants may
  // share one canonicalCardId, so prefer the published instrument identity.
  const rowKey = (row) => row.instrumentId || row.cardVariantId || row[idField] || row.rank;
  const columns = buildConstituentColumns(asset, movementWindow);
  const primaryColumn = columns.find((column) => column.primary);
  const page = useMarketExplorerConstituentPage(identity, { cache: pageCache });
  const previewOnly = mode === "preview";
  const visibleRows = previewOnly ? page.rows.slice(0, PREVIEW_ROWS) : page.rows;
  const mismatch = prepared && page.errorCode === CONSTITUENT_ERROR.generationMismatch
    && page.errorSpecKey === (identity ? JSON.stringify(identity) : null);
  const refreshedFor = useRef(null);
  // The directory generation changed after this market loaded. Reload the
  // market (fresh generationId); the identity change then re-pages from rank 0.
  // Rows from two generations are never mixed. Attempted once per generation.
  useEffect(() => {
    if (!mismatch) return;
    const token = `${series.key}:${series.generationId}`;
    if (refreshedFor.current === token) return;
    refreshedFor.current = token;
    onRefreshPrepared?.(series.key);
  }, [mismatch, series.key, series.generationId, onRefreshPrepared]);
  const retryLoad = () => {
    if (mismatch) { refreshedFor.current = null; onRefreshPrepared?.(series.key); return; }
    page.retry();
  };

  if (page.isLoading && page.rows.length === 0) {
    return (
      <p role="status" data-market-constituents-page-loading className="px-3 pb-6 pt-1 text-xs text-[var(--text-secondary)] sm:px-4">
        Loading constituents…
      </p>
    );
  }
  if (page.error && page.rows.length === 0) {
    const message = prepared ? (PREPARED_ERROR_COPY[page.errorCode] || PREPARED_ERROR_COPY.default) : page.error;
    // LOCKED is a deliberate product state, not a failure: constituents are an
    // Index+ feature. It is distinct from unavailable / failed / empty / loading.
    if (prepared && NON_RETRYABLE.has(page.errorCode)) {
      return (
        <div role="status" data-market-constituents-state="locked" data-market-constituents-locked={page.errorCode} className="mx-3 mb-6 mt-1 rounded-lg border border-violet-400/40 bg-violet-500/[.08] px-3 py-3 text-xs text-[var(--text-secondary)] sm:mx-4">
          <strong className="block text-[var(--text-primary)]">Constituents are included with Index+</strong>
          <span className="block">{page.errorCode === CONSTITUENT_ERROR.auth ? "Sign in with an Index+ plan to see what is inside this market." : "Upgrade to Index+ to see what is inside this market."}</span>
          <a href={page.errorCode === CONSTITUENT_ERROR.auth ? "/login" : "/pricing"} data-market-constituents-locked-link className="mt-2 inline-block rounded-md border border-violet-300/60 px-2.5 py-1 font-semibold text-violet-100">{page.errorCode === CONSTITUENT_ERROR.auth ? "Sign in" : "See Index+"}</a>
        </div>
      );
    }
    return (
      <div className="px-3 pb-6 pt-1 sm:px-4">
        <p role="alert" data-market-constituents-state="failed" data-market-constituents-page-error className="text-xs text-[var(--text-secondary)]">
          {message}
        </p>
        {NON_RETRYABLE.has(page.errorCode) ? null : (
          <button
            type="button"
            data-market-constituents-page-retry
            onClick={retryLoad}
            className="mt-2 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
          >
            Retry
          </button>
        )}
      </div>
    );
  }
  if (prepared && page.isReady && page.rows.length === 0) {
    return (
      <p role="status" data-market-constituents-state={page.availability || "unavailable"} className="px-3 pb-6 pt-1 text-xs text-[var(--text-secondary)] sm:px-4">
        {PREPARED_STATE_COPY[page.availability] || PREPARED_STATE_COPY.unavailable}
      </p>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-3 pb-2 sm:px-4">
        <span data-market-constituents-page-count className="text-[10px] text-[var(--text-secondary)]">
          Showing <span className="tabular-nums">{visibleRows.length}</span> of{" "}
          <span className="tabular-nums" data-market-constituents-count>{page.totalCount}</span>
          {asset === "sealed" ? " products" : " cards"}
          {page.asOf ? ` · as of ${page.asOf}` : ""}
        </span>
      </div>
      <div data-market-constituents-table className="hidden overflow-x-auto px-3 pb-2 sm:px-4 desk:block">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="border-y border-[var(--border-subtle)] text-[10px] uppercase tracking-[0.07em] text-[var(--text-secondary)]">
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col" className={`px-3 py-2 ${column.align === "right" ? "text-right" : ""}`}>
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={rowKey(row)} data-market-constituent={rowKey(row)} className="border-b border-[var(--border-subtle)] last:border-0">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={[
                      "px-3 py-2",
                      column.align === "right" ? "text-right" : "",
                      column.numeric || column.price ? "tabular-nums" : "",
                      column.primary ? "font-medium text-[var(--text-primary)]" : "",
                    ].join(" ")}
                  >
                    {column.change ? (
                      <ChangeCell row={row} window={column.window} label={cellValue(row, primaryColumn)} />
                    ) : column.primary ? (
                      <span className="inline-flex min-w-0 items-center gap-2">
                        <ConstituentThumbnail row={row} asset={asset} />
                        <span className="min-w-0 truncate">{cellValue(row, column)}</span>
                        {asset === "cards" ? <VariantBadge row={row} /> : null}
                      </span>
                    ) : cellValue(row, column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-market-constituents-cards className="space-y-1.5 px-3 pb-2 sm:px-4 desk:hidden">
        {visibleRows.map((row) => (
          <li key={rowKey(row)} data-market-constituent={rowKey(row)} className="flex items-start gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/30 px-2.5 py-2">
            <span className="w-5 flex-none pt-0.5 text-[10px] tabular-nums text-[var(--text-secondary)]">{row.rank}</span>
            <ConstituentThumbnail row={row} asset={asset} className="h-12 w-9" />
            <span className="min-w-0 flex-1">
              <span className="flex min-w-0 items-center">
                <span className="min-w-0 truncate text-xs font-medium text-[var(--text-primary)]">{cellValue(row, primaryColumn)}</span>
                {asset === "cards" ? <VariantBadge row={row} /> : null}
              </span>
              <span className="block truncate text-[10px] text-[var(--text-secondary)]">
                {row.setName || "—"} · {asset === "sealed" ? (row.productFamilyLabel || "—") : (row.rarity || "—")}
              </span>
            </span>
            <span className="flex flex-none flex-col items-end pt-0.5">
              <span className="text-xs font-semibold tabular-nums text-[var(--text-primary)]">{formatBasketValue(row.marketPrice)}</span>
            </span>
          </li>
        ))}
      </ul>
      {prepared && page.rows.length > 0 && !hasAnyConstituentMovement(page.rows, movementWindow) ? (
        <p data-market-constituents-movement-unavailable className="px-3 pb-2 text-[10px] text-[var(--text-secondary)] sm:px-4">
          Constituent movement is not available for this timeframe.
        </p>
      ) : null}
      {page.error ? (
        <div className="px-3 pb-4 sm:px-4">
          <p role="alert" data-market-constituents-state="failed" data-market-constituents-page-error className="text-xs text-[var(--text-secondary)]">
            {prepared ? (PREPARED_ERROR_COPY[page.errorCode] || PREPARED_ERROR_COPY.default) : page.error}
          </p>
          {NON_RETRYABLE.has(page.errorCode) ? null : (
            <button type="button" data-market-constituents-page-retry onClick={retryLoad}
              className="mt-2 rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]">
              Retry
            </button>
          )}
        </div>
      ) : previewOnly ? null : page.hasMore ? (
        <div className="px-3 pb-4 sm:px-4">
          <button
            type="button"
            data-market-constituents-load-more
            onClick={page.loadMore}
            disabled={page.isLoadingMore}
            className="rounded-full border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] disabled:opacity-50"
          >
            {page.isLoadingMore ? "Loading more…" : `Load more (${page.totalCount - page.rows.length} remaining)`}
          </button>
        </div>
      ) : (
        <p data-market-constituents-page-complete className="px-3 pb-4 text-[10px] text-[var(--text-secondary)] sm:px-4">
          All {page.totalCount} constituents loaded.
        </p>
      )}
    </>
  );
}

export default function MarketExplorerConstituents({
  selectedSeries = [],
  activeSeriesId = null,
  onSelectSeries,
  onEditSeries,
  mode = "expanded",
  onRefreshPrepared,
  hiddenSeriesKeys = null,
  focusedSeriesKey = null,
  pageCache = null,
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
  // Active markets that publish no roster are SAID, never silently skipped.
  const notInspectable = selectedSeries.filter((series) => series && !(series.available !== false && isEnumerableSeries(series)));
  const notInspectableReason = (series) => resolveCompositionCapability(series).reason
    || series.unavailableReason
    || `${series.label || "This market"} composition is not available in the current published generation.`;
  // A QUERY-BUILT market pages its roster from the backend; a prepared/parent
  // market keeps reading its already-published (small) summary.
  const isQuerySourced = Boolean(active?.queryFingerprint);
  // A PREPARED market pages its roster from the backend, pinned to the
  // generation it was loaded from. Identity is the backend-published
  // { key, generationId }; nothing is derived from labels.
  const isPrepared = !isQuerySourced && Boolean(active?.generationId && active?.marketType);
  const isPaged = isQuerySourced || isPrepared;
  const pagedIdentity = isQuerySourced ? (active?.spec || null)
    : isPrepared ? { marketKey: active.key, generationId: active.generationId } : null;
  const model = resolveSeriesConstituents(active, { movementWindow });
  const primaryColumn = model.columns.find((column) => column.primary);

  return (
    <section
      data-market-explorer-constituents
      data-market-constituents-asset={isPaged ? resolveSeriesAsset(active) : model.asset}
      data-market-constituents-availability={isPaged ? CONSTITUENTS_AVAILABLE : model.availability}
      data-market-constituents-source={isQuerySourced ? "query-paged" : isPrepared ? "prepared-paged" : "published"}
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
            {!isPaged && model.availability === CONSTITUENTS_AVAILABLE ? (
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
            {notInspectable.length && !inspectable.length ? "No inspectable market is active." : "Select a market to see what is inside it."}
          </span>
        )}
        {(isPaged || model.availability === CONSTITUENTS_AVAILABLE) ? (
          <div className="ml-auto">
            <MovementWindowSelector value={model.movementWindow} onChange={setMovementWindow} />
          </div>
        ) : null}
        {active?.instanceId && active?.spec?.membershipMode === "explicit" ? (
          <button type="button" data-market-constituents-edit-items onClick={() => onEditSeries?.(active)} className="min-h-9 rounded-md border border-[var(--border-subtle)] px-3 text-[11px] font-semibold text-[var(--text-secondary)]">Edit Items</button>
        ) : null}
      </div>

      <ConstituentSwitcher
        entries={buildConstituentSwitcherEntries(selectedSeries.filter(Boolean), { targetKey: active?.key || null, hiddenKeys: hiddenSeriesKeys instanceof Set ? hiddenSeriesKeys : new Set(), focusedKey: focusedSeriesKey })}
        onSelect={onSelectSeries}
      />

      {notInspectable.length ? (
        <ul data-market-constituents-not-inspectable className="space-y-0.5 px-3 pb-2 text-[10px] text-[var(--text-secondary)] sm:px-4">
          {notInspectable.map((series) => (
            <li key={series.key} data-market-constituents-not-inspectable-item={series.key}>
              <span className="font-semibold text-[var(--text-primary)]">{series.shortLabel || series.label}</span>: {notInspectableReason(series)}
            </li>
          ))}
        </ul>
      ) : null}

      {isPaged ? (
        // NEVER the 33k-row static path — always the paged backend consumer.
        <QueryConstituentSection series={active} identity={pagedIdentity} movementWindow={movementWindow}
          mode={mode} prepared={isPrepared} onRefreshPrepared={onRefreshPrepared} pageCache={pageCache} />
      ) : model.availability === CONSTITUENTS_AVAILABLE ? (
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
                            <ConstituentThumbnail row={row} asset={model.asset} />
                            <span className="min-w-0 truncate">{cellValue(row, column)}</span>
                            {model.asset === "cards" ? <VariantBadge row={row} /> : null}
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
                <ConstituentThumbnail row={row} asset={model.asset} className="h-12 w-9" />
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-center">
                    <span className="min-w-0 truncate text-xs font-medium text-[var(--text-primary)]">
                      {cellValue(row, primaryColumn)}
                    </span>
                    {model.asset === "cards" ? <VariantBadge row={row} /> : null}
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
            : (model.reason || (!active && notInspectable.length && !inspectable.length ? "None of the active markets publishes an inspectable composition right now." : "Select a market to see what is inside it."))}
        </p>
      )}
    </section>
  );
}

export { CONSTITUENTS_AVAILABLE, CONSTITUENTS_NOT_APPLICABLE, CONSTITUENTS_PENDING_PUBLICATION };
