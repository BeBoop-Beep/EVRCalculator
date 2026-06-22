function padDatePart(value) {
  return String(value).padStart(2, "0");
}

export function parseDateOnlyParts(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }

  return {
    year: Number(match[1]),
    monthIndex: Number(match[2]) - 1,
    day: Number(match[3]),
  };
}

function formatDateKeyFromParts(year, month, day) {
  return `${year}-${padDatePart(month)}-${padDatePart(day)}`;
}

function formatLocalDateKey(date) {
  return formatDateKeyFromParts(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

export function getLocalHistoryDateKey(date = new Date()) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return null;
  }
  return formatLocalDateKey(date);
}

export function getHistoryDateKey(value) {
  if (!value) {
    return null;
  }

  const text = String(value || "").trim();
  const dateOnlyText = text.slice(0, 10);
  if (parseDateOnlyParts(dateOnlyText)) {
    return dateOnlyText;
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return formatLocalDateKey(date);
}

export function addDaysToHistoryDateKey(value, days) {
  const dateOnly = parseDateOnlyParts(value);
  if (!dateOnly) {
    return null;
  }

  const date = new Date(Date.UTC(dateOnly.year, dateOnly.monthIndex, dateOnly.day));
  date.setUTCDate(date.getUTCDate() + days);
  return formatDateKeyFromParts(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

export function formatHistoryDate(value, options = {}) {
  if (!value) {
    return null;
  }

  const dateOnly = parseDateOnlyParts(value);
  if (dateOnly) {
    return new Intl.DateTimeFormat("en-US", {
      ...options,
      timeZone: "UTC",
    }).format(new Date(Date.UTC(dateOnly.year, dateOnly.monthIndex, dateOnly.day)));
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat("en-US", options).format(date);
}
