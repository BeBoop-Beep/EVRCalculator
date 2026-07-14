import { computeDeltaWindowsFromHistory } from "../../lib/explore/marketDeltaWindows.mjs";

const SHORT_WINDOW_KEYS = new Set(["1D", "7D", "30D"]);

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateKey(value) {
  const resolved = String(value || "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(resolved) ? resolved : null;
}

function storedWindows(card) {
  if (card?.marketDeltaWindows && typeof card.marketDeltaWindows === "object") {
    return card.marketDeltaWindows;
  }
  if (card?.market_delta_windows && typeof card.market_delta_windows === "object") {
    return card.market_delta_windows;
  }
  return null;
}

function identityMismatch(stored, card, camel, snake) {
  const movementValue = stored?.[camel] ?? stored?.[snake];
  const cardValue = card?.[camel] ?? card?.[snake];
  return Boolean(movementValue && cardValue && String(movementValue) !== String(cardValue));
}

export function getTopCardStoredMovement(card, selectedWindowKey) {
  if (!SHORT_WINDOW_KEYS.has(selectedWindowKey)) return null;
  const raw = storedWindows(card)?.[selectedWindowKey];
  if (!raw || typeof raw !== "object") return null;

  const startDate = dateKey(raw?.startDate ?? raw?.start_date);
  const endDate = dateKey(raw?.endDate ?? raw?.end_date);
  const amount = toFiniteNumber(raw?.changeAmount ?? raw?.change_amount);
  const percent = toFiniteNumber(raw?.changePercent ?? raw?.change_percent);
  const malformed = (
    (amount === null && percent === null)
    || !startDate
    || !endDate
    || startDate >= endDate
    || identityMismatch(raw, card, "cardVariantId", "card_variant_id")
    || identityMismatch(raw, card, "conditionId", "condition_id")
  );

  if (malformed) {
    return { raw, valid: false, reason: "malformed_stored_window" };
  }

  return {
    ...raw,
    valid: true,
    key: selectedWindowKey,
    label: selectedWindowKey,
    amount,
    percent,
    startDate,
    endDate,
    targetStartDate: dateKey(raw?.targetStartDate ?? raw?.target_start_date),
    currentPrice: toFiniteNumber(raw?.currentPrice ?? raw?.current_price),
    isSinceFirstAvailable: Boolean(raw?.isPartialWindow ?? raw?.is_partial_window),
    source: "stored-canonical",
  };
}

export function getTopCardHistoryWindow(historyPoints, selectedWindowKey) {
  const windows = computeDeltaWindowsFromHistory(historyPoints, {
    dateKey: "date",
    valueKey: "value",
    preferActualPointsForOneDay: false,
  });
  return windows.find((entry) => entry.key === selectedWindowKey) || null;
}

function latestVisiblePrice(historyPoints, chartWindow) {
  if (!chartWindow?.endDate) return null;
  const candidates = (Array.isArray(historyPoints) ? historyPoints : [])
    .filter((point) => dateKey(point?.date) && dateKey(point.date) <= chartWindow.endDate)
    .sort((left, right) => String(left.date).localeCompare(String(right.date)));
  return toFiniteNumber(candidates.at(-1)?.value);
}

export function resolveTopCardWindowState({ card, historyPoints, selectedWindowKey }) {
  const historyMovement = getTopCardHistoryWindow(historyPoints, selectedWindowKey);
  const storedResult = getTopCardStoredMovement(card, selectedWindowKey);
  const storedMovement = storedResult?.valid ? storedResult : null;
  const warnings = [];

  if (!SHORT_WINDOW_KEYS.has(selectedWindowKey)) {
    return {
      chartWindow: historyMovement,
      displayMovement: historyMovement,
      storedMovement: null,
      historyMovement,
      source: historyMovement ? "history" : "insufficient_history",
      warnings,
    };
  }

  if (storedResult && !storedResult.valid) {
    warnings.push(storedResult.reason);
  } else if (!storedResult) {
    warnings.push("missing_stored_window");
  }

  if (storedMovement && historyMovement) {
    const mismatches = [];
    if (storedMovement.startDate !== historyMovement.startDate) mismatches.push("startDate");
    if (storedMovement.endDate !== historyMovement.endDate) mismatches.push("endDate");
    const historyCurrentPrice = latestVisiblePrice(historyPoints, historyMovement);
    if (
      storedMovement.currentPrice !== null
      && historyCurrentPrice !== null
      && Math.abs(storedMovement.currentPrice - historyCurrentPrice) >= 0.005
    ) {
      mismatches.push("currentPrice");
    }
    if (mismatches.length > 0) {
      warnings.push(`stored_history_mismatch:${mismatches.join(",")}`);
    }
  }

  if (storedMovement) {
    return {
      chartWindow: historyMovement,
      displayMovement: storedMovement,
      storedMovement,
      historyMovement,
      source: "stored-canonical",
      warnings,
    };
  }

  if (historyMovement) {
    return {
      chartWindow: historyMovement,
      displayMovement: {
        ...historyMovement,
        source: storedResult ? "history_fallback_malformed_stored_window" : "history_fallback_missing_stored_window",
      },
      storedMovement: null,
      historyMovement,
      source: storedResult ? "history_fallback_malformed_stored_window" : "history_fallback_missing_stored_window",
      warnings,
    };
  }

  return {
    chartWindow: null,
    displayMovement: null,
    storedMovement: null,
    historyMovement: null,
    source: "insufficient_history",
    warnings,
  };
}

export function getTopCardPreferredHistoryEndDate(card, selectedWindowKey, historyPoints) {
  const rawStored = storedWindows(card)?.[selectedWindowKey];
  const storedEndDate = dateKey(rawStored?.endDate ?? rawStored?.end_date);
  const marketDate = dateKey(card?.marketDate ?? card?.market_date);
  const dashboardDate = dateKey(card?.dashboardLatestMarketDate ?? card?.dashboard_latest_market_date);
  const snapshotEndDate = marketDate || dashboardDate;
  if (storedEndDate && snapshotEndDate) return storedEndDate < snapshotEndDate ? storedEndDate : snapshotEndDate;
  if (storedEndDate) return storedEndDate;
  if (snapshotEndDate) return snapshotEndDate;

  return (Array.isArray(historyPoints) ? historyPoints : [])
    .map((point) => dateKey(point?.date))
    .filter(Boolean)
    .sort()
    .at(-1) || null;
}

export function warnForTopCardWindowState(windowState, card, selectedWindowKey) {
  if (process.env.NODE_ENV === "production" || !windowState?.warnings?.length) return;
  for (const warning of windowState.warnings) {
    console.warn("[pokemon-market-delta] Top Chase window fallback/mismatch", {
      canonicalCardId: card?.canonicalCardId || card?.cardId || card?.id,
      window: selectedWindowKey,
      warning,
      source: windowState.source,
      storedMovement: windowState.storedMovement,
      historyMovement: windowState.historyMovement,
      movementGeneration: card?.movementGeneration || null,
    });
  }
}
