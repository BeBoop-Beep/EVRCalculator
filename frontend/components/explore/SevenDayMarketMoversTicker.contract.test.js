const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const source = fs.readFileSync(
  path.resolve(__dirname, "SevenDayMarketMoversTicker.jsx"),
  "utf8"
);

test("Explore mode widens shared ticker items while set mode keeps its original sizing", () => {
  assert.ok(source.includes('crossSet ? "w-[13.5rem] sm:w-[15rem]" : ""'));
  assert.ok(source.includes('crossSet ? "min-w-0 flex-1" : "min-w-0 max-w-[11rem]"'));
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
});
