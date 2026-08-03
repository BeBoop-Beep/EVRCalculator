// Formatting shared by the homepage previews. One place so the same number
// never appears in two shapes on the same page.

export const currency2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const currency0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const signedCurrency0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  signDisplay: "always",
  maximumFractionDigits: 0,
});

const monthDay = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const monthDayYear = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

function parseIsoDate(isoDate) {
  if (typeof isoDate !== "string" || !isoDate.trim()) return null;
  const parsed = new Date(`${isoDate.trim().slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatAsOf(isoDate) {
  const parsed = parseIsoDate(isoDate);
  return parsed ? monthDay.format(parsed) : null;
}

export function formatFullDate(isoDate) {
  const parsed = parseIsoDate(isoDate);
  return parsed ? monthDayYear.format(parsed) : null;
}

/** `prob_profit` arrives as a 0-1 share. */
export function formatProbability(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${(value * 100).toFixed(0)}%`;
}

export function formatSignedPercent(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function getInitials(name) {
  const words = String(name || "")
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return "PK";
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}
