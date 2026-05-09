"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import PremiumTimeSeriesChart from "@/components/charts/PremiumTimeSeriesChart";

const CardDetailMarketContext = createContext(null);

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toCurrency(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parsed);
}

function formatPercent(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  return `${parsed.toFixed(2)}%`;
}

function formatShortDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatLongDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

function buildGradedLabel(row) {
  if (!row) {
    return "Graded";
  }
  const company = String(row?.grading_company_name || "").trim();
  const specialLabel = String(row?.special_label || "").trim();
  const gradeValue = String(row?.grade_value ?? "").trim();

  if (specialLabel && gradeValue && company) {
    return `${company} ${specialLabel} ${gradeValue}`;
  }
  if (company && gradeValue) {
    return `${company} ${gradeValue}`;
  }
  if (specialLabel && gradeValue) {
    return `${specialLabel} ${gradeValue}`;
  }
  return company || specialLabel || (gradeValue ? `Grade ${gradeValue}` : "Graded");
}

function toSeriesSlug(value) {
  return String(value || "series")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "series";
}

const PERIOD_OPTIONS = [
  { key: "1D", label: "1D", days: 1 },
  { key: "7D", label: "7D", days: 7 },
  { key: "1M", label: "1M", days: 30 },
  { key: "6M", label: "6M", days: 183 },
  { key: "1Y", label: "1Y", days: 365 },
  { key: "LT", label: "LT", days: null },
];

const TREND_EPSILON_PERCENT = 0.1;
const TREND_EPSILON_ABSOLUTE = 0.01;

function parseDateValue(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

function selectDefaultRawConditionId(conditionPrices) {
  const rows = Array.isArray(conditionPrices) ? conditionPrices : [];
  if (!rows.length) {
    return "";
  }
  const nearMint = rows.find((row) => String(row?.condition || "").toLowerCase().includes("near mint"));
  return String((nearMint || rows[0])?.condition_id || "");
}

function selectDefaultGradedId(gradedPrices) {
  const rows = Array.isArray(gradedPrices) ? gradedPrices : [];
  if (!rows.length) {
    return "";
  }

  const psa10 = rows.find((row) => {
    const company = String(row?.grading_company_name || "").trim().toLowerCase();
    const grade = toNumber(row?.grade_value);
    return company === "psa" && grade === 10;
  });
  if (psa10?.graded_card_variant_id !== undefined && psa10?.graded_card_variant_id !== null) {
    return String(psa10.graded_card_variant_id);
  }

  const sortedByGrade = [...rows].sort((a, b) => {
    const aGrade = toNumber(a?.grade_value);
    const bGrade = toNumber(b?.grade_value);
    return (bGrade ?? -1) - (aGrade ?? -1);
  });

  return String((sortedByGrade[0] || rows[0])?.graded_card_variant_id || "");
}

function normalizeHistoryPoints(points) {
  const rows = Array.isArray(points) ? points : [];
  return rows
    .map((point, index) => {
      const date = point?.date || null;
      const marketPrice = toNumber(point?.market_price);
      return {
        id: `${date || "na"}:${index}`,
        date,
        market_price: marketPrice,
        high_price: toNumber(point?.high_price),
        low_price: toNumber(point?.low_price),
        source: point?.source || null,
      };
    })
    .filter((point) => point.date && point.market_price !== null)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function getWindowedPoints(points, periodKey) {
  const rows = Array.isArray(points) ? points : [];
  if (!rows.length) {
    return [];
  }
  if (periodKey === "LT") {
    return rows;
  }

  const period = PERIOD_OPTIONS.find((option) => option.key === periodKey);
  const days = period?.days;
  if (!days) {
    return rows;
  }

  const latestDate = parseDateValue(rows[rows.length - 1]?.date);
  if (!latestDate) {
    return rows;
  }
  const threshold = new Date(latestDate.getTime() - days * 24 * 60 * 60 * 1000);
  return rows.filter((point) => {
    const pointDate = parseDateValue(point?.date);
    return pointDate ? pointDate >= threshold : false;
  });
}

function computeDeltaFromPoints(points, periodKey) {
  const scopedPoints = getWindowedPoints(points, periodKey);
  if (scopedPoints.length < 2) {
    return null;
  }

  const first = scopedPoints[0];
  const last = scopedPoints[scopedPoints.length - 1];
  const firstPrice = toNumber(first?.market_price);
  const lastPrice = toNumber(last?.market_price);
  if (firstPrice === null || lastPrice === null) {
    return null;
  }

  const absolute = lastPrice - firstPrice;
  const percent = firstPrice === 0 ? null : (absolute / firstPrice) * 100;
  return {
    absolute,
    percent,
    from_date: first?.date || null,
    to_date: last?.date || null,
  };
}

function inferDefaultPeriod(points) {
  if (computeDeltaFromPoints(points, "7D")) {
    return "7D";
  }
  if (computeDeltaFromPoints(points, "1M")) {
    return "1M";
  }
  return "LT";
}

function buildSingleSeriesChartData(series, periodKey, chartMode) {
  if (!series) return [];
  const scopedPoints = getWindowedPoints(series.points || [], periodKey);
  if (!scopedPoints.length) return [];

  const baseline = toNumber(scopedPoints[0]?.market_price);
  return scopedPoints
    .map((point) => {
      const date = point?.date;
      if (!date) return null;
      const marketPrice = toNumber(point?.market_price);
      if (chartMode === "price") {
        return { date, value: marketPrice };
      }
      const absD = marketPrice !== null && baseline !== null ? marketPrice - baseline : null;
      const pct = baseline !== null && baseline !== 0 && absD !== null ? (absD / baseline) * 100 : null;
      return { date, value: absD, value__pct: pct };
    })
    .filter(Boolean)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function computeTrendInfo(points, periodKey) {
  const delta = computeDeltaFromPoints(Array.isArray(points) ? points : [], periodKey);
  const absolute = toNumber(delta?.absolute);
  const percentMagnitude = Math.abs(toNumber(delta?.percent) ?? 0);

  if (absolute !== null) {
    if (Math.abs(absolute) < TREND_EPSILON_ABSOLUTE || percentMagnitude < TREND_EPSILON_PERCENT) {
      return { direction: "flat", trend: "neutral" };
    }
    return absolute > 0
      ? { direction: "up", trend: "positive" }
      : { direction: "down", trend: "negative" };
  }

  const windowed = getWindowedPoints(Array.isArray(points) ? points : [], periodKey);
  if (windowed.length < 2) {
    return { direction: "flat", trend: "neutral" };
  }

  const first = toNumber(windowed[0]?.market_price);
  const last = toNumber(windowed[windowed.length - 1]?.market_price);
  if (first === null || last === null) {
    return { direction: "flat", trend: "neutral" };
  }

  const fallbackAbsolute = last - first;
  if (Math.abs(fallbackAbsolute) < TREND_EPSILON_ABSOLUTE) {
    return { direction: "flat", trend: "neutral" };
  }

  return fallbackAbsolute > 0
    ? { direction: "up", trend: "positive" }
    : { direction: "down", trend: "negative" };
}

function getDeltaDirection(delta) {
  const absolute = toNumber(delta?.absolute);
  const percentMagnitude = Math.abs(toNumber(delta?.percent) ?? 0);
  if (absolute === null) {
    return null;
  }
  if (Math.abs(absolute) < TREND_EPSILON_ABSOLUTE || percentMagnitude < TREND_EPSILON_PERCENT) {
    return "flat";
  }
  return absolute > 0 ? "up" : "down";
}

function isDeltaFallback(delta, periodKey) {
  if (!delta?.from_date || !delta?.to_date) return false;
  const period = PERIOD_OPTIONS.find((p) => p.key === periodKey);
  if (!period?.days) return false;
  const fromDate = new Date(delta.from_date);
  const toDate = new Date(delta.to_date);
  if (Number.isNaN(fromDate.getTime()) || Number.isNaN(toDate.getTime())) return false;
  const actualDays = (toDate - fromDate) / (24 * 60 * 60 * 1000);
  return actualDays < period.days * 0.7;
}

function useCardDetailMarket() {
  const context = useContext(CardDetailMarketContext);
  if (!context) {
    throw new Error("CardDetailMarket components must be used inside CardDetailMarketProvider");
  }
  return context;
}

function PillToggle({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1">
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold tracking-[0.04em] transition ${
              isActive
                ? "bg-brand text-white shadow-[0_0_0_1px_rgba(20,184,166,0.35)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function PriceHistoryTooltip({ active, payload, conditionLabel, chartMode }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const item = payload.find((p) => p.dataKey === "value");
  if (!item) return null;
  const absVal = toNumber(item.value);
  const pctVal = toNumber(row.value__pct);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[rgba(6,9,18,0.97)] px-4 py-3 shadow-[0_24px_48px_rgba(0,0,0,0.6)] backdrop-blur-md ring-1 ring-white/[0.06]">
      {conditionLabel ? (
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">{conditionLabel}</p>
      ) : null}
      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{formatLongDate(row.date)}</p>
      <div className="mt-2">
        {chartMode === "price" ? (
          <p className="text-sm font-semibold text-[var(--text-primary)]">{toCurrency(absVal)}</p>
        ) : (
          <>
            <p
              className="text-sm font-semibold"
              style={{
                color: absVal !== null && absVal >= 0 ? "rgba(20,184,166,0.95)" : "rgba(239,68,68,0.88)",
              }}
            >
              Delta: {absVal !== null ? `${absVal >= 0 ? "+" : ""}${toCurrency(absVal)}` : "-"}
            </p>
            {pctVal !== null ? (
              <p
                className="mt-0.5 text-xs"
                style={{
                  color: pctVal >= 0 ? "rgba(20,184,166,0.78)" : "rgba(239,68,68,0.74)",
                }}
              >
                {pctVal >= 0 ? "+" : ""}{pctVal.toFixed(1)}%
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function PriceHistoryChart({
  activeSeries,
  period,
  onPeriodChange,
  chartMode,
  onChartModeChange,
  emptyMessage,
}) {
  const chartData = useMemo(
    () => buildSingleSeriesChartData(activeSeries, period, chartMode),
    [activeSeries, period, chartMode]
  );

  const trendInfo = useMemo(
    () => computeTrendInfo(activeSeries?.points || [], period),
    [activeSeries, period]
  );

  return (
    <PremiumTimeSeriesChart
      title="Market History"
      subtitle={activeSeries?.label ? `Selected: ${activeSeries.label}` : "Select a condition or grade to inspect trend"}
      data={chartData}
      selectedPeriod={period}
      periods={PERIOD_OPTIONS.map((option) => ({ value: option.key, label: option.label }))}
      onPeriodChange={onPeriodChange}
      selectedMode={chartMode}
      onModeChange={onChartModeChange}
      trend={trendInfo.trend}
      mode={chartMode}
      formatValue={toCurrency}
      formatXAxisLabel={formatShortDate}
      tooltipContent={
        <PriceHistoryTooltip
          conditionLabel={activeSeries?.label || null}
          chartMode={chartMode}
        />
      }
      emptyMessage={emptyMessage}
      className="rounded-2xl"
    />
  );
}

function formatDelta(delta) {
  if (!delta) {
    return null;
  }
  const absolute = toNumber(delta?.absolute);
  const percent = toNumber(delta?.percent);
  if (absolute === null || percent === null) {
    return null;
  }
  const absPrefix = absolute >= 0 ? "+" : "";
  const pctPrefix = percent >= 0 ? "+" : "";
  return `${absPrefix}${toCurrency(absolute)} / ${pctPrefix}${percent.toFixed(1)}%`;
}

export function CardDetailMarketProvider({ conditionPrices = [], gradedPrices = [], priceHistory = {}, children }) {
  const safeConditionPrices = Array.isArray(conditionPrices) ? conditionPrices : [];
  const safeGradedPrices = Array.isArray(gradedPrices) ? gradedPrices : [];

  const [marketType, setMarketType] = useState("raw");
  const [selectedConditionId, setSelectedConditionId] = useState(selectDefaultRawConditionId(safeConditionPrices));
  const [selectedGradedId, setSelectedGradedId] = useState(selectDefaultGradedId(safeGradedPrices));
  const [selectedPeriod, setSelectedPeriod] = useState("7D");
  const [chartMode, setChartMode] = useState("price");

  const rawHistory = useMemo(
    () =>
      (Array.isArray(priceHistory?.raw) ? priceHistory.raw : []).map((row) => ({
        id: String(row?.condition_id || "unknown-condition"),
        key: `raw-${toSeriesSlug(row?.condition_id)}`,
        label: row?.condition || "Condition",
        points: normalizeHistoryPoints(row?.points || []),
        sourceDelta: row?.delta || null,
      })),
    [priceHistory]
  );

  const gradedHistory = useMemo(
    () =>
      (Array.isArray(priceHistory?.graded) ? priceHistory.graded : []).map((row) => ({
        id: String(row?.graded_card_variant_id || "unknown-graded"),
        key: `graded-${toSeriesSlug(row?.graded_card_variant_id)}`,
        label: buildGradedLabel(row),
        points: normalizeHistoryPoints(row?.points || []),
        sourceDelta: row?.delta || null,
      })),
    [priceHistory]
  );

  const selectedRawPriceRow = useMemo(() => {
    if (!safeConditionPrices.length) {
      return null;
    }
    const selected = safeConditionPrices.find((row) => String(row?.condition_id) === String(selectedConditionId));
    return selected || safeConditionPrices[0] || null;
  }, [safeConditionPrices, selectedConditionId]);

  const selectedGradedPriceRow = useMemo(() => {
    if (!safeGradedPrices.length) {
      return null;
    }
    const selected = safeGradedPrices.find((row) => String(row?.graded_card_variant_id) === String(selectedGradedId));
    return selected || safeGradedPrices[0] || null;
  }, [safeGradedPrices, selectedGradedId]);

  const selectedRawHistorySeries = useMemo(() => {
    const selected = rawHistory.find((row) => String(row?.id) === String(selectedRawPriceRow?.condition_id));
    return selected || null;
  }, [rawHistory, selectedRawPriceRow]);

  const selectedGradedHistorySeries = useMemo(() => {
    const selected = gradedHistory.find(
      (row) => String(row?.id) === String(selectedGradedPriceRow?.graded_card_variant_id)
    );
    return selected || null;
  }, [gradedHistory, selectedGradedPriceRow]);

  const hasGradedPrices = safeGradedPrices.length > 0;
  const effectiveMarketType = marketType === "graded" && !hasGradedPrices ? "raw" : marketType;
  const activeSeries = effectiveMarketType === "graded" ? selectedGradedHistorySeries : selectedRawHistorySeries;
  const visibleSeries = effectiveMarketType === "graded" ? gradedHistory : rawHistory;

  useEffect(() => {
    const activePoints = activeSeries?.points || [];
    const hasCurrentPeriodData = computeDeltaFromPoints(activePoints, selectedPeriod) !== null || selectedPeriod === "LT";
    if (!hasCurrentPeriodData) {
      setSelectedPeriod(inferDefaultPeriod(activePoints));
    }
  }, [activeSeries, selectedPeriod]);

  const selectedPriceCard = useMemo(() => {
    if (effectiveMarketType === "graded") {
      if (!selectedGradedPriceRow) {
        return {
          title: "Current Selected Price",
          amount: "Price unavailable",
          label: "No graded prices",
          source: null,
          capturedAt: null,
          deltaText: null,
        };
      }

      const gradedDelta = computeDeltaFromPoints(selectedGradedHistorySeries?.points || [], selectedPeriod);
      return {
        title: "Current Selected Price",
        amount: toCurrency(selectedGradedPriceRow?.market_price),
        label: buildGradedLabel(selectedGradedPriceRow),
        source: selectedGradedPriceRow?.source || selectedGradedPriceRow?.grading_company_name || null,
        capturedAt: selectedGradedPriceRow?.created_at || null,
        deltaText: formatDelta(gradedDelta),
        deltaDirection: getDeltaDirection(gradedDelta),
        isFallbackHistory: isDeltaFallback(gradedDelta, selectedPeriod),
      };
    }

    if (!selectedRawPriceRow) {
      return {
        title: "Current Selected Price",
        amount: "Price unavailable",
        label: "No raw condition prices",
        source: null,
        capturedAt: null,
        deltaText: null,
        deltaDirection: null,
        isFallbackHistory: false,
      };
    }

    const rawDelta = computeDeltaFromPoints(selectedRawHistorySeries?.points || [], selectedPeriod);
    return {
      title: "Current Selected Price",
      amount: toCurrency(selectedRawPriceRow?.market_price),
      label: selectedRawPriceRow?.condition || "Condition",
      source: selectedRawPriceRow?.source || null,
      capturedAt: selectedRawPriceRow?.captured_at || selectedRawPriceRow?.created_at || null,
      deltaText: formatDelta(rawDelta),
      deltaDirection: getDeltaDirection(rawDelta),
      isFallbackHistory: isDeltaFallback(rawDelta, selectedPeriod),
    };
  }, [
    effectiveMarketType,
    selectedGradedPriceRow,
    selectedRawPriceRow,
    selectedGradedHistorySeries,
    selectedRawHistorySeries,
    selectedPeriod,
  ]);

  const selectedSeriesId = effectiveMarketType === "graded"
    ? String(selectedGradedPriceRow?.graded_card_variant_id || "")
    : String(selectedRawPriceRow?.condition_id || "");

  const value = {
    marketType,
    setMarketType,
    effectiveMarketType,
    hasGradedPrices,
    conditionPrices: safeConditionPrices,
    gradedPrices: safeGradedPrices,
    selectedConditionId,
    setSelectedConditionId,
    selectedGradedId,
    setSelectedGradedId,
    selectedPeriod,
    setSelectedPeriod,
    chartMode,
    setChartMode,
    selectedRawPriceRow,
    selectedGradedPriceRow,
    selectedPriceCard,
    selectedSeriesId,
    activeSeries,
    visibleSeries,
  };

  return <CardDetailMarketContext.Provider value={value}>{children}</CardDetailMarketContext.Provider>;
}

export function CardDetailSelectedPriceCard() {
  const {
    marketType,
    setMarketType,
    effectiveMarketType,
    hasGradedPrices,
    conditionPrices,
    gradedPrices,
    selectedConditionId,
    setSelectedConditionId,
    selectedGradedId,
    setSelectedGradedId,
    selectedPeriod,
    setSelectedPeriod,
    selectedPriceCard,
  } = useCardDetailMarket();

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3 sm:col-span-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Market Type</p>
        <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1">
          <button
            type="button"
            onClick={() => setMarketType("raw")}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              effectiveMarketType === "raw"
                ? "bg-brand text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            Raw
          </button>
          <button
            type="button"
            onClick={() => setMarketType("graded")}
            disabled={!hasGradedPrices}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              effectiveMarketType === "graded"
                ? "bg-brand text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            } ${!hasGradedPrices ? "cursor-not-allowed opacity-50" : ""}`}
          >
            Graded
          </button>
        </div>
      </div>

      <div className="mt-3">
        {effectiveMarketType === "raw" ? (
          <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Raw Condition
            <select
              className="mt-1 w-full cursor-pointer appearance-none rounded-md border border-[rgba(148,163,184,0.26)] bg-[linear-gradient(180deg,rgba(10,15,27,0.95),rgba(6,10,20,0.96))] px-3 py-2 pr-8 text-sm font-semibold tracking-[0.01em] text-[var(--text-primary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05),inset_0_0_0_1px_rgba(0,0,0,0.28)] outline-none transition duration-200 hover:border-[rgba(20,184,166,0.4)] focus:border-[rgba(20,184,166,0.55)] focus:ring-2 focus:ring-[rgba(20,184,166,0.28)]"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='rgba(20,184,166,0.7)' d='M1 1l5 5 5-5'/%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat',
                backgroundPosition: 'right 8px center',
              }}
              value={selectedConditionId}
              onChange={(event) => setSelectedConditionId(event.target.value)}
            >
              {conditionPrices.map((row) => {
                const price = toNumber(row?.market_price);
                const priceStr = price !== null ? ` — ${toCurrency(price)}` : "";
                return (
                  <option key={String(row?.condition_id || "condition")} value={String(row?.condition_id || "")}>
                    {`${row?.condition || "Condition"}${priceStr}`}
                  </option>
                );
              })}
            </select>
          </label>
        ) : (
          <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
            Graded Option
            <select
              className="mt-1 w-full cursor-pointer appearance-none rounded-md border border-[rgba(148,163,184,0.26)] bg-[linear-gradient(180deg,rgba(10,15,27,0.95),rgba(6,10,20,0.96))] px-3 py-2 pr-8 text-sm font-semibold tracking-[0.01em] text-[var(--text-primary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05),inset_0_0_0_1px_rgba(0,0,0,0.28)] outline-none transition duration-200 hover:border-[rgba(20,184,166,0.4)] focus:border-[rgba(20,184,166,0.55)] focus:ring-2 focus:ring-[rgba(20,184,166,0.28)]"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='rgba(20,184,166,0.7)' d='M1 1l5 5 5-5'/%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat',
                backgroundPosition: 'right 8px center',
              }}
              value={selectedGradedId}
              onChange={(event) => setSelectedGradedId(event.target.value)}
              disabled={!gradedPrices.length}
            >
              {gradedPrices.length === 0 ? <option value="">No graded prices available</option> : null}
              {gradedPrices.map((row) => (
                <option key={String(row?.graded_card_variant_id || "graded")} value={String(row?.graded_card_variant_id || "") }>
                  {buildGradedLabel(row)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Current Selected Price</p>
          <PillToggle
            value={selectedPeriod}
            onChange={setSelectedPeriod}
            options={PERIOD_OPTIONS.map((period) => ({ value: period.key, label: period.label }))}
          />
        </div>
        <p className="text-lg font-semibold text-[var(--text-primary)]">{selectedPriceCard.amount}</p>
        
        {/* Delta directly under price */}
        {selectedPriceCard.deltaText ? (
          <p
            className="mt-1 text-xs font-semibold"
            style={{
              color:
                selectedPriceCard.deltaDirection === "up"
                  ? "rgba(20,184,166,0.92)"
                  : selectedPriceCard.deltaDirection === "down"
                  ? "rgba(239,68,68,0.88)"
                  : "var(--text-secondary)",
            }}
          >
            {selectedPriceCard.deltaText} {selectedPeriod}
          </p>
        ) : null}
        
        <p className="mt-2 text-sm text-[var(--text-secondary)]">{selectedPriceCard.label}</p>
        {selectedPriceCard.source ? (
          <p className="mt-1 text-xs text-[var(--text-secondary)]">Source: {selectedPriceCard.source}</p>
        ) : null}
        {selectedPriceCard.capturedAt ? (
          <p className="text-xs text-[var(--text-secondary)]">Captured: {formatLongDate(selectedPriceCard.capturedAt)}</p>
        ) : null}
        {selectedPriceCard.isFallbackHistory ? (
          <p className="mt-0.5 text-[11px] italic text-[var(--text-secondary)]/60">Based on available history</p>
        ) : null}
      </div>

      {marketType === "graded" && !hasGradedPrices ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">No graded prices are available for this card variant yet.</p>
      ) : null}
    </div>
  );
}

export function CardDetailMarketHistorySection() {
  const {
    selectedPeriod,
    setSelectedPeriod,
    chartMode,
    setChartMode,
    activeSeries,
  } = useCardDetailMarket();

  return (
    <PriceHistoryChart
      activeSeries={activeSeries}
      period={selectedPeriod}
      onPeriodChange={setSelectedPeriod}
      chartMode={chartMode}
      onChartModeChange={setChartMode}
      emptyMessage={
        !activeSeries
          ? "No history is available for the selected market type yet."
          : "No history points are available in the selected time window."
      }
    />
  );
}
