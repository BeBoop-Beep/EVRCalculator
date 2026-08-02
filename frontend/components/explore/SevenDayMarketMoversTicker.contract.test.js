const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const source = fs.readFileSync(
  path.resolve(__dirname, "SevenDayMarketMoversTicker.jsx"),
  "utf8"
);

test("both modes retain compact item width while Explore alone receives extra height", () => {
  assert.ok(!source.includes("w-[13.5rem]"));
  assert.ok(!source.includes("sm:w-[15rem]"));
  assert.ok(source.includes('className="min-w-0 max-w-[11rem]"'));
  assert.ok(source.includes('const containerHeightClass = crossSet ? "h-20" : "h-14";'));
  assert.ok(source.includes("`set-glass-surface flex ${containerHeightClass} min-w-0 items-center"));
});

test("the optional medium thumbnail is larger and responsive without changing the default set size", () => {
  assert.ok(source.includes('thumbnailSize = "small"'));
  assert.ok(source.includes('thumbnailSize === "medium"'));
  assert.ok(source.includes('"h-12 w-[2.1rem] max-desk:h-11 max-desk:w-[1.925rem]"'));
  assert.ok(source.includes(': "h-10 w-7"'));
  assert.ok(source.includes("items-center justify-center overflow-hidden"));
  assert.ok(source.includes('className="h-full w-full object-contain"'));
  assert.ok(!source.includes("object-cover"));
});

test("set identity remains exclusive to Explore mode", () => {
  assert.ok(
    source.includes(
      'crossSet ? <span className="block truncate text-[10px] text-[var(--text-secondary)]">{card?.setName || "Unknown set"}</span> : null'
    )
  );
});

test("both modes continue through the single shared item implementation", () => {
  assert.equal((source.match(/function Item\(/g) || []).length, 1);
  assert.equal((source.match(/function SevenDayMarketMoversTicker\(/g) || []).length, 1);
  assert.ok(source.includes("crossSet={crossSet}"));
  assert.equal((source.match(/<MoversTickerViewport/g) || []).length, 1);
});

test("set action uses one responsive accessible anchor and Explore still omits it", () => {
  assert.ok(source.includes("!crossSet && viewAllHref ? <a href={viewAllHref}"));
  assert.ok(source.includes('aria-label="View all 7-day movers"'));
  assert.ok(source.includes("h-10 w-10 flex-none items-center justify-center"));
  assert.ok(source.includes('className="desk:hidden" aria-hidden="true"'));
  assert.ok(source.includes('className="h-4 w-4"'));
  assert.ok(source.includes('d="m7.5 4.5 5 5-5 5"'));
  assert.ok(source.includes('className="hidden text-xs font-semibold desk:inline"'));
  assert.ok(source.includes("View all movers →"));
  assert.equal((source.match(/aria-label="View all 7-day movers"/g) || []).length, 1);
  const mobileChild = source.slice(
    source.indexOf('<span className="desk:hidden"'),
    source.indexOf('<span className="hidden text-xs font-semibold desk:inline"')
  );
  assert.ok(!mobileChild.includes("View all movers"));
});

test("Explore cards use canonical shared set routing and ignore false setSlug values", () => {
  assert.ok(source.includes('import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting"'));
  assert.ok(source.includes("const setName = card?.setName || card?.set_name;"));
  assert.ok(source.includes("if (!targetId || !setName) return fallback;"));
  assert.ok(source.includes('{ target_type: "set", target_id: targetId, name: setName }'));
  assert.ok(source.includes('{ tab: "cards", section: "market-movers", window: "7D" }'));
  assert.ok(!source.includes("card?.setSlug"));
  assert.ok(source.includes("href={crossSet ? hrefFor(card, viewAllHref) : viewAllHref}"));
});
