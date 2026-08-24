const DATE_KEY = /^\d{4}-\d{2}-\d{2}$/;

export function clipSetMarketDetailHistory(history, movement) {
  const startDate = String(movement?.startDate || "").slice(0, 10);
  const endDate = String(movement?.endDate || "").slice(0, 10);
  return (Array.isArray(history) ? history : [])
    .filter((point) => {
      const date = String(point?.date || "").slice(0, 10);
      const value = Number(point?.setValue);
      if (!DATE_KEY.test(date) || !Number.isFinite(value)) return false;
      if (startDate && date < startDate) return false;
      if (endDate && date > endDate) return false;
      return true;
    })
    .sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

export function needsLifetimeSetMarketHistory({ activeWindowKey, historyStartDate, loadedHistory, loadedDays }) {
  if (activeWindowKey !== "lifetime" || Number(loadedDays) >= 1825) return false;
  const firstLoadedDate = String(loadedHistory?.[0]?.date || "").slice(0, 10);
  const firstAvailableDate = String(historyStartDate || "").slice(0, 10);
  return Boolean(DATE_KEY.test(firstLoadedDate) && DATE_KEY.test(firstAvailableDate) && firstAvailableDate < firstLoadedDate);
}
