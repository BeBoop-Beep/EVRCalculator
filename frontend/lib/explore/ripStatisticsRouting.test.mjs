import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (file) => fs.readFileSync(path.resolve(here, file), "utf8").replace(/\r\n/g, "\n");
const slugifySource = read("../../utils/slugify.js")
  .replace(/export function/g, "function")
  .replace(/\btoSetSlug\b/g, "toCanonicalSetSlug");
const routingSource = read("ripStatisticsRouting.js").replace(
  /^import \{[^}]*\} from "@\/utils\/slugify";\n/m,
  ""
);
const { buildTcgSetHrefFromSlug, buildTcgSetHrefFromTarget } = await import(
  `data:text/javascript;base64,${Buffer.from(`${slugifySource}\n${routingSource}`, "utf8").toString("base64")}`
);

test("set slug routes preserve the requested set and default to RIP", () => {
  assert.equal(
    buildTcgSetHrefFromSlug("perfect-order"),
    "/TCGs/Pokemon/Sets/perfect-order"
  );
});

const setTarget = (name) => ({
  target_type: "set",
  target_id: "142d3869-9d39-48b6-a810-751af2aac748",
  name,
});

test("canonical set names drive mover routes and validated windows", () => {
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), {
      tab: "cards", section: "market-movers", window: "7d",
    }),
    "/TCGs/Pokemon/Sets/journey-together?tab=cards&section=market-movers&window=7D"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Prismatic Evolutions")),
    "/TCGs/Pokemon/Sets/prismatic-evolutions"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Scarlet and Violet 151")),
    "/TCGs/Pokemon/Sets/scarlet-and-violet-151"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), {
      tab: "cards", section: "market-movers", window: "30D",
    }),
    "/TCGs/Pokemon/Sets/journey-together?tab=cards&section=market-movers&window=30D"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), {
      tab: "cards", section: "market-movers", window: "1Y",
    }),
    "/TCGs/Pokemon/Sets/journey-together?tab=cards&section=market-movers"
  );
});

test("the default tab is never written into an internal href — Top Rankings links to the bare canonical set URL", () => {
  // `overview` is the default view, so `?tab=overview` and the bare path render
  // the same page. The bare path is what the set page declares as canonical, so
  // internal links must not point at the query variant of it.
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), { tab: "overview" }),
    "/TCGs/Pokemon/Sets/journey-together"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together")),
    "/TCGs/Pokemon/Sets/journey-together"
  );
  // A non-default tab still travels, and so does a section on the default tab.
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), { tab: "market" }),
    "/TCGs/Pokemon/Sets/journey-together?tab=market"
  );
  assert.equal(
    buildTcgSetHrefFromTarget(setTarget("Journey Together"), { tab: "overview", section: "rip-score" }),
    "/TCGs/Pokemon/Sets/journey-together?section=rip-score"
  );
});
