import { SET_PRODUCT_FAMILY_ORDER } from "./setProductComparison.mjs";

const LABELS = Object.freeze({
  loose_booster_pack: "Loose Booster Pack",
  sleeved_booster_pack: "Sleeved Booster Pack",
  booster_bundle: "Booster Bundle",
  elite_trainer_box: "Elite Trainer Box",
  half_booster_box: "Half Booster Box",
  pokemon_center_elite_trainer_box: "Pokémon Center ETB",
  booster_box: "Booster Box",
  enhanced_booster_box: "Enhanced Booster Box",
});

export const displaySetPackFamily = (family) => LABELS[family] || String(family || "Product family")
  .split("_").filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");

export const orderSetPackFamilies = (rows) => [...(rows || [])].sort((a, b) => {
  const ai = SET_PRODUCT_FAMILY_ORDER.indexOf(a.family);
  const bi = SET_PRODUCT_FAMILY_ORDER.indexOf(b.family);
  return (ai < 0 ? SET_PRODUCT_FAMILY_ORDER.length : ai) - (bi < 0 ? SET_PRODUCT_FAMILY_ORDER.length : bi);
});
