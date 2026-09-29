import { money, ratioAsPercent } from "./openingEconomicsSelector.mjs";

const finite = (value) => value !== null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;

export const SET_PACK_COLUMNS = Object.freeze([
  ["productFamilyCount", "Families"], ["productCount", "Products"],
  ["averagePackCostPerPack", "Avg Pack Cost"], ["expectedValuePerPack", "EV / Pack"],
  ["modeledReturnOnSpend", "Modeled Return"], ["chanceToRecoverCost", "Recover Cost"],
  ["entertainmentCostPerPack", "Entertainment Cost"], ["bestOpenPrice", "Best-Open Price"],
]);

export const ECONOMIC_KEYS = Object.freeze(SET_PACK_COLUMNS.slice(2, 7).map(([key]) => key));

export function sortPackEconomicsSets(sets = [], key = "modeledReturnOnSpend", direction = "desc") {
  const sign = direction === "asc" ? 1 : -1;
  return [...sets].sort((left, right) => {
    if (key === "setName") return sign * String(left.setName || "").localeCompare(String(right.setName || ""));
    const a = finite(left?.[key]), b = finite(right?.[key]);
    if (a === null) return b === null ? String(left.setName || "").localeCompare(String(right.setName || "")) : 1;
    if (b === null) return -1;
    return sign * (a - b) || String(left.setName || "").localeCompare(String(right.setName || ""));
  });
}

export function formatPackEconomicsValue(key, value) {
  if (["productFamilyCount", "productCount"].includes(key)) return finite(value) === null ? null : String(Number(value));
  if (["modeledReturnOnSpend", "chanceToRecoverCost"].includes(key)) return ratioAsPercent(value);
  return money(value);
}

export function familyBestOpenPresentation(family) {
  if (family?.bestOpenDisplayMode === "multiple") return `${family?.products?.length || family?.productCount || 0} prices`;
  return formatPackEconomicsValue("bestOpenPrice", family?.products?.[0]?.bestOpenPrice) || "—";
}

export function filterPackEconomicsSets(sets = [], query = "", eraFilter = null) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  const era = String(eraFilter || "").trim().toLocaleLowerCase();
  return sets.filter((row) => (!era || String(row?.era?.eraName || "").toLocaleLowerCase() === era) && (!needle || `${row?.setName || ""} ${row?.era?.eraName || ""}`.toLocaleLowerCase().includes(needle)));
}
