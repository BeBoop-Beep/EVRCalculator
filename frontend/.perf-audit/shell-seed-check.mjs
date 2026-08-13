import fs from "node:fs";
import { adaptSetShell } from "../lib/pokemon/set-page/setPageAdapters.mjs";
const dir = "C:/Users/Owner/AppData/Local/Temp/claude/d--EVRCalculator/85861793-771a-47aa-95cc-4d8d924b1fff/scratchpad";
for (const s of ["ascendedheroes", "shroudedfable", "prismaticevolutions", "scarletandviolet151"]) {
  const raw = JSON.parse(fs.readFileSync(`${dir}/shell_${s}.json`, "utf8"));
  const c = adaptSetShell(raw);
  const vp = c?.setValueSummary?.compact?.visiblePoints;
  console.log(
    s.padEnd(22),
    "visiblePoints=", Array.isArray(vp) ? vp.length : JSON.stringify(vp),
    "| currentValue=", c?.setValueSummary?.currentValue,
    "| delta30d=", c?.setValueSummary?.delta30dAmount,
    "| sourceKey=", c?.setValueSummary?.sourceKey
  );
}
