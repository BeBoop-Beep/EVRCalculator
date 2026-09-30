const number = (value) => value === null || value === undefined || value === "" ? null : Number.isFinite(Number(value)) ? Number(value) : null;

export const PRODUCT_SCORE_COLUMNS = ["Rank", "Product", "Product Overall", "Financial", "Set Chase", "Set Collector"];
export const PRODUCT_ECONOMICS_COLUMNS = ["Product", "Unit Price", "Best-Open Price", "EV / Pack", "Modeled Return", "Recover Cost"];

export function productFamilyOptions(rows = []) {
  const values = new Map();
  for (const row of rows || []) if (row?.familyKey && !values.has(row.familyKey)) values.set(row.familyKey, row.familyName || row.familyKey);
  return [...values].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
}

export function filterProductRows(rows = [], { query = "", family = "all" } = {}) {
  const needle = query.trim().toLocaleLowerCase();
  return (rows || []).filter((row) => (family === "all" || row.familyKey === family) && (!needle || [row.productName, row.setName, row.familyName].some((value) => String(value || "").toLocaleLowerCase().includes(needle))));
}

export function sortProductRows(rows = [], key, direction = "asc") {
  const multiplier = direction === "desc" ? -1 : 1;
  const score = (row) => key === "productName" ? String(row.productName || "") : key === "ripScore" ? number(row.ripScore?.scoreValue) : number(row[key]);
  return [...rows].sort((a, b) => {
    const left = score(a), right = score(b);
    if (typeof left === "string" || typeof right === "string") return String(left).localeCompare(String(right)) * multiplier;
    if (left === null && right === null) return String(a.productName).localeCompare(String(b.productName));
    if (left === null) return 1;
    if (right === null) return -1;
    return (left - right) * multiplier || String(a.productName).localeCompare(String(b.productName));
  });
}

export function bestOpenGap(row) {
  const dollars = number(row?.bestOpenPriceGapDollars), percent = number(row?.bestOpenPriceGapPercent);
  if (dollars === null && percent === null) return null;
  const headroom = row?.bestOpenStatus === "current_number_one_with_headroom";
  const money = dollars === null ? null : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Math.abs(dollars));
  const ratio = percent === null ? null : `${(Math.abs(percent) * 100).toFixed(1)}%`;
  return `${money || ratio} ${headroom ? "headroom" : "below market"}${money && ratio ? ` · ${ratio}` : ""}`;
}

export function bestOpenDetails(row = {}) {
  const threshold = number(row.bestOpenPrice);
  const marketPrice = number(row.bestOpenMarketPrice ?? row.marketPrice);
  const available = threshold !== null;
  const difference = available && marketPrice !== null ? marketPrice - threshold : null;
  const percentDifference = difference !== null && marketPrice !== 0 ? difference / marketPrice : null;
  const signedMoney = difference === null ? null : `${difference >= 0 ? "+" : "−"}$${Math.abs(difference).toFixed(2)}`;
  const signedPercent = percentDifference === null ? null : `${percentDifference >= 0 ? "+" : "−"}${(Math.abs(percentDifference) * 100).toFixed(1)}%`;
  const interpretation = difference === null ? null : difference > 0
    ? `Current market price is $${Math.abs(difference).toFixed(2)} above the modeled Best-Open threshold.`
    : difference < 0
      ? `Current market price is $${Math.abs(difference).toFixed(2)} below the modeled Best-Open threshold.`
      : "Current market price equals the modeled Best-Open threshold.";
  return { available, threshold, marketPrice, difference, percentDifference,
    differenceText: signedMoney ? `${signedMoney}${signedPercent ? ` · ${signedPercent}` : ""}` : null,
    interpretation, bestOpenDate: row.bestOpenSourceMarketDate || null,
    marketDate: row.bestOpenMarketSourceDate || row.economicsSourceMarketDate || null,
    status: row.bestOpenStatus || "unavailable", freshness: row.bestOpenFreshnessStatus || null };
}
