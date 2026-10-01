const finite = (value) => typeof value === "number" && Number.isFinite(value);

export function orderMarketPerformanceReadings(readings, focusedSeriesKey = null) {
  const visible = focusedSeriesKey
    ? readings.filter((reading) => reading.key === focusedSeriesKey)
    : [...readings];
  return visible.sort((left, right) => {
    const leftAvailable = finite(left.value);
    const rightAvailable = finite(right.value);
    if (leftAvailable !== rightAvailable) return leftAvailable ? -1 : 1;
    if (leftAvailable && left.value !== right.value) return right.value - left.value;
    return String(left.key).localeCompare(String(right.key));
  });
}
