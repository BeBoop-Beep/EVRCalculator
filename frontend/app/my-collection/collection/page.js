import MyCollectionPageClient from "@/components/Profile/MyCollectionPageClient";
import { getPrivateCollectionEntries } from "@/lib/profile/collectionEntryLoader";

const ALLOWED_SORTS = new Set(["recent", "value-desc", "value-asc", "name-asc", "name-desc"]);
const ALLOWED_VIEWS = new Set(["continuous", "binder"]);
const ALLOWED_TYPES = new Set(["cards", "sealed", "merchandise"]);
const ALLOWED_CONDITIONS = new Set([
  "mint",
  "near-mint",
  "lightly-played",
  "moderately-played",
  "heavily-played",
  "sealed",
]);

function readParamValue(searchParams, key) {
  const raw = searchParams?.[key];
  if (Array.isArray(raw)) {
    return String(raw[0] || "").trim();
  }
  return String(raw || "").trim();
}

export default async function MyCollectionPage({ searchParams }) {
  const resolvedSearchParams = (await searchParams) || {};
  const initialItems = await getPrivateCollectionEntries();

  const q = readParamValue(resolvedSearchParams, "q");
  const sort = readParamValue(resolvedSearchParams, "sort");
  const view = readParamValue(resolvedSearchParams, "view");
  const type = readParamValue(resolvedSearchParams, "type");
  const condition = readParamValue(resolvedSearchParams, "condition");
  const tcg = readParamValue(resolvedSearchParams, "tcg");

  const localToolState = {
    q,
    sort: ALLOWED_SORTS.has(sort) ? sort : "recent",
    view: ALLOWED_VIEWS.has(view) ? view : "continuous",
    type: ALLOWED_TYPES.has(type) ? type : "",
    condition: ALLOWED_CONDITIONS.has(condition) ? condition : "",
    tcg: tcg || "",
  };

  return <MyCollectionPageClient initialItems={initialItems} localNavToolState={localToolState} />;
}
