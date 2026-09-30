"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useMarketExplorerConstituentPage from "@/hooks/explore/useMarketExplorerConstituentPage";
import {
  fetchMarketActivityConstituents,
  fetchMarketActivityInstrument,
} from "@/lib/explore/marketActivityApi.mjs";
import {
  validateActivityConstituentResponse,
  validateActivityInstrumentResponse,
} from "@/lib/explore/marketActivityState.mjs";

const ACTIVITY_PAGE_LIMIT = 50;

const formatMoney = (money) =>
  money?.amount
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: money.currency || "USD",
      }).format(Number(money.amount))
    : "—";
const fact = (value) => (value === null || value === undefined ? "—" : value);
const reasonLabel = (reason) =>
  String(reason || "Unavailable")
    .replaceAll("_", " ")
    .toLowerCase();
const inFlightActivityPages = new Map();

function exactJoin(activityRow, canonicalByVariant) {
  const canonical = canonicalByVariant.get(activityRow.cardVariantId);
  if (
    !canonical ||
    activityRow.instrumentKey !== `card:${activityRow.cardVariantId}:raw`
  )
    return null;
  return { ...activityRow, display: canonical };
}

function useActivityPage({ scope, enabled, fixtureMode }) {
  const [state, setState] = useState({
    status: "idle",
    rows: [],
    page: null,
    error: null,
    cursor: null,
  });
  const sequence = useRef(0);
  const load = useCallback(
    async (cursor = null, append = false) => {
      if (!scope) return;
      const requestSequence = ++sequence.current;
      setState((current) => ({
        ...current,
        status: append ? "loadingMore" : "loading",
        error: null,
      }));
      try {
        const limit = fixtureMode ? 2 : ACTIVITY_PAGE_LIMIT;
        const requestKey = JSON.stringify({
          ...scope,
          cursor,
          limit,
          fixtureMode,
        });
        let request = inFlightActivityPages.get(requestKey);
        if (!request) {
          request = fixtureMode
            ? import("@/lib/explore/marketActivityFixtures.mjs").then(
                ({ loadMarketActivityFixture }) =>
                  loadMarketActivityFixture({
                    fixtureId: cursor ? "fma_fixture_16" : "fma_fixture_10",
                  }),
              )
            : fetchMarketActivityConstituents({ ...scope, cursor, limit });
          inFlightActivityPages.set(requestKey, request);
          request.finally(() => inFlightActivityPages.delete(requestKey));
        }
        const payload = validateActivityConstituentResponse(
          await request,
          scope,
          { cursor, limit },
        );
        if (requestSequence !== sequence.current) return;
        if (payload.availability?.state === "UNAVAILABLE") {
          setState({
            status: "unavailable",
            rows: [],
            page: payload.page,
            error: payload.availability.reasons,
            cursor: null,
          });
          return;
        }
        setState((current) => ({
          status: "ready",
          rows: append ? [...current.rows, ...payload.rows] : payload.rows,
          page: payload.page,
          error: null,
          cursor: payload.page?.nextCursor || null,
        }));
      } catch (error) {
        if (requestSequence !== sequence.current) return;
        setState((current) => ({ ...current, status: "error", error }));
      }
    },
    [scope, fixtureMode],
  );
  useEffect(() => {
    sequence.current += 1;
    setState({
      status: "idle",
      rows: [],
      page: null,
      error: null,
      cursor: null,
    });
    if (enabled && scope) load();
    return () => {
      sequence.current += 1;
    };
  }, [enabled, scope, load]);
  return {
    ...state,
    retry: () => load(state.cursor, state.rows.length > 0),
    loadMore: () => load(state.cursor, true),
  };
}

function InstrumentDrawer({ row, scope, chartRange, fixtureMode, onClose }) {
  const [state, setState] = useState({
    status: "loading",
    data: null,
    error: null,
  });
  useEffect(() => {
    const controller = new AbortController();
    const requestedChartRange = fixtureMode ? null : chartRange;
    const request = fixtureMode
      ? import("@/lib/explore/marketActivityFixtures.mjs").then(
          ({ loadMarketActivityFixture }) =>
            loadMarketActivityFixture({
              fixtureId: "fma_fixture_01",
              signal: controller.signal,
            }),
        )
      : fetchMarketActivityInstrument({
          ...scope,
          instrumentKey: row.instrumentKey,
          chartRange: requestedChartRange,
          signal: controller.signal,
        });
    request
      .then((payload) => {
        if (controller.signal.aborted) return;
        const data = validateActivityInstrumentResponse(payload, scope, {
          instrumentKey: row.instrumentKey,
          cardVariantId: row.cardVariantId,
          chartRange: requestedChartRange,
          tier: scope.tier,
        });
        setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ status: "error", data: null, error });
      });
    return () => controller.abort();
  }, [row.instrumentKey, row.cardVariantId, scope, chartRange, fixtureMode]);
  const data = state.data;
  const windowRows = data?.sales?.windows || [];
  const selected = selectSalesWindow(windowRows, scope.windowDays);
  return (
    <div
      data-market-activity-instrument
      role="dialog"
      aria-modal="true"
      aria-labelledby="activity-instrument-heading"
      className="fixed inset-y-0 right-0 z-[100] w-full max-w-lg overflow-y-auto border-l border-sky-400/35 bg-slate-950 p-5 shadow-2xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-sky-300">
            Exact instrument
          </p>
          <h3
            id="activity-instrument-heading"
            className="text-lg font-semibold text-white"
          >
            {row.display.cardName || row.display.name || "Card activity"}
          </h3>
          <p className="text-xs text-slate-400">
            {row.display.edition || row.display.editionLabel || "Exact edition"}{" "}
            ·{" "}
            {row.display.printing ||
              row.display.printingLabel ||
              "Exact printing"}
          </p>
        </div>
        <button
          type="button"
          autoFocus
          onClick={onClose}
          className="min-h-10 rounded border border-slate-600 px-3 text-xs text-white"
        >
          Close
        </button>
      </div>
      {state.status === "loading" ? (
        <p role="status" className="mt-6 text-sm text-slate-300">
          Loading instrument activity…
        </p>
      ) : null}
      {state.status === "error" ? (
        <p role="alert" className="mt-6 text-sm text-rose-300">
          Instrument activity is temporarily unavailable.
        </p>
      ) : null}
      {data?.availability?.state === "UNAVAILABLE" ? (
        <p className="mt-6 text-sm text-amber-200">
          {data.availability.reasons.map(reasonLabel).join(", ")}
        </p>
      ) : null}
      {data?.instrument ? (
        <div className="mt-5 space-y-5 text-sm text-slate-200">
          <section>
            <h4 className="font-semibold text-white">Coverage</h4>
            <p>
              {data.instrument.tier === "RAW"
                ? "Raw"
                : `${data.instrument.grading?.grader} ${data.instrument.grading?.grade}`}{" "}
              · observed {fact(selected?.observedCount)} · proven{" "}
              {fact(selected?.provenCount)}
            </p>
            <p className="text-xs text-slate-400">
              Graded activity is unavailable unless an exact graded instrument
              is published.
            </p>
          </section>
          <section>
            <h4 className="font-semibold text-white">Observed sales</h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {windowRows.map((window) => (
                <div
                  key={window.days}
                  className="rounded border border-slate-700 p-2"
                >
                  <strong>{window.days}D</strong>
                  <br />
                  Observed {fact(window.observedCount)} · Proven{" "}
                  {fact(window.provenCount)}
                </div>
              ))}
            </div>
            <p className="mt-2">
              Median {formatMoney(selected?.priceSummary?.median)} · Low{" "}
              {formatMoney(selected?.priceSummary?.low)} · High{" "}
              {formatMoney(selected?.priceSummary?.high)}
              {selected?.priceSummary?.recordCount != null
                ? ` · ${selected.priceSummary.recordCount} records`
                : ""}
            </p>
          </section>
          <section>
            <h4 className="font-semibold text-white">Offered Supply</h4>
            <p>
              {reasonLabel(data.asks?.state)} · Lowest ask{" "}
              {formatMoney(data.asks?.lowestAsk?.price)} · Captured listings{" "}
              {fact(data.asks?.capturedListingCount)} · Captured quantity{" "}
              {fact(data.asks?.capturedQuantity?.value)}
            </p>
            <p className="text-xs text-slate-400">
              Source confirmation{" "}
              {data.asks?.providerConfirmedAt || "not established"}
            </p>
          </section>
          <section>
            <h4 className="font-semibold text-white">Peer context</h4>
            {data.peers?.state === "AVAILABLE" ? (
              <p>
                {data.peers.activityPercentile} percentile among{" "}
                {data.peers.eligibleOtherPeerCount} other peers ·{" "}
                {data.peers.scopeLabel}
              </p>
            ) : (
              <p>
                {(data.peers?.reasons || ["INSUFFICIENT_PEERS"])
                  .map(reasonLabel)
                  .join(", ")}
              </p>
            )}
          </section>
          {data.availability?.reasons?.length ? (
            <section>
              <h4 className="font-semibold text-white">Unavailable details</h4>
              <p>{data.availability.reasons.map(reasonLabel).join(", ")}</p>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function MarketActivityConstituents({
  series,
  capability,
  identity,
  pageCache,
  chartRange = null,
  fixtureMode = false,
}) {
  const canonical = useMarketExplorerConstituentPage(identity, {
    limit: 50,
    cache: pageCache,
  });
  const scope = useMemo(
    () =>
      capability
        ? {
            marketKey: capability.marketKey,
            activityGenerationId: capability.activityGenerationId,
            rosterRef: capability.rosterRef,
            asOf: capability.asOf,
            windowDays: capability.windowDays,
            tier: capability.tier || capability.grade,
          }
        : null,
    [capability],
  );
  const activity = useActivityPage({
    scope,
    enabled: Boolean(scope),
    fixtureMode,
  });
  const [opened, setOpened] = useState(null);
  const canonicalByVariant = useMemo(
    () =>
      new Map(
        canonical.rows
          .filter((row) => row.cardVariantId)
          .map((row) => [row.cardVariantId, row]),
      ),
    [canonical.rows],
  );
  const rows = useMemo(
    () =>
      activity.rows
        .map((row) => exactJoin(row, canonicalByVariant))
        .filter(Boolean),
    [activity.rows, canonicalByVariant],
  );
  if (canonical.isLoading || activity.status === "loading")
    return (
      <p role="status" className="px-3 pb-6 text-xs text-slate-400">
        Loading constituent activity…
      </p>
    );
  if (activity.status === "unavailable")
    return (
      <p role="status" className="px-3 pb-6 text-xs text-amber-200">
        Activity unavailable:{" "}
        {(activity.error || []).map(reasonLabel).join(", ")}.
      </p>
    );
  if (canonical.error || activity.status === "error")
    return (
      <div className="px-3 pb-6">
        <p role="alert" className="text-xs text-rose-300">
          Activity temporarily unavailable.
        </p>
        <button
          type="button"
          onClick={activity.retry}
          className="mt-2 rounded border border-slate-600 px-2 py-1 text-xs"
        >
          Retry
        </button>
      </div>
    );
  return (
    <div data-market-constituents-activity>
      {activity.rows.length !== rows.length ? (
        <p role="status" className="px-3 pb-2 text-[10px] text-amber-200">
          Some rows were withheld because exact variant display identity was
          unavailable.
        </p>
      ) : null}
      <div className="hidden overflow-x-auto px-3 pb-3 desk:block">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead className="border-y border-slate-700 text-[10px] uppercase text-slate-400">
            <tr>
              <th className="px-2 py-2">Card</th>
              <th>Observed Sales</th>
              <th>Proven Sales</th>
              <th>Median Sale</th>
              <th>Ask State / Lowest Ask</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.instrumentKey} className="border-b border-slate-800">
                <td className="px-2 py-2">
                  <button
                    type="button"
                    onClick={() => setOpened(row)}
                    className="text-left font-medium text-sky-100 underline-offset-2 hover:underline"
                  >
                    {row.display.cardName ||
                      row.display.name ||
                      row.cardVariantId}
                  </button>
                </td>
                <td>{fact(row.observedCount)}</td>
                <td>{fact(row.provenCount)}</td>
                <td>{formatMoney(row.medianPrice)}</td>
                <td>
                  {reasonLabel(row.askState)} /{" "}
                  {formatMoney(row.lowestAsk?.price)}
                </td>
                <td>{reasonLabel(row.windowReadiness)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul
        data-market-activity-mobile-cards
        className="space-y-2 px-3 pb-3 desk:hidden"
      >
        {rows.map((row) => (
          <li key={row.instrumentKey}>
            <button
              type="button"
              onClick={() => setOpened(row)}
              className="w-full rounded-lg border border-slate-700 p-3 text-left"
            >
              <strong className="block text-sm text-white">
                {row.display.cardName || row.display.name || row.cardVariantId}
              </strong>
              <span className="text-xs text-slate-300">
                Observed {fact(row.observedCount)} · Proven{" "}
                {fact(row.provenCount)} · Median {formatMoney(row.medianPrice)}
              </span>
              <span className="block text-[10px] text-slate-400">
                {reasonLabel(row.askState)} ·{" "}
                {formatMoney(row.lowestAsk?.price)} ·{" "}
                {reasonLabel(row.windowReadiness)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {activity.cursor && canonical.hasMore ? (
        <button
          type="button"
          data-market-activity-load-more
          disabled={
            activity.status === "loadingMore" || canonical.isLoadingMore
          }
          onClick={() => {
            canonical.loadMore();
            activity.loadMore();
          }}
          className="mx-3 mb-4 rounded border border-slate-600 px-3 py-1.5 text-xs"
        >
          {activity.status === "loadingMore" ? "Loading…" : "Load more"}
        </button>
      ) : null}
      {opened ? (
        <InstrumentDrawer
          row={opened}
          scope={scope}
          chartRange={chartRange}
          fixtureMode={fixtureMode}
          onClose={() => setOpened(null)}
        />
      ) : null}
    </div>
  );
}

export { exactJoin };
export function selectSalesWindow(windows, days) {
  return windows.find((entry) => entry.days === days) || null;
}
