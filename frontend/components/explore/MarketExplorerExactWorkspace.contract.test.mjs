import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const picker = read("./MarketExplorerExactItemPicker.jsx");
const builder = read("./MarketExplorerQueryBuilder.jsx");
const constituents = read("./MarketExplorerConstituents.jsx");

test("one dedicated responsive workspace owns the exact browser", () => {
  assert.equal((builder.match(/<MarketExplorerExactItemPicker/g) || []).length, 1);
  assert.doesNotMatch(builder, /<ExplorerDisclosure[^>]+ExactItems/);
  assert.match(builder, /data-market-exact-open/);
  for (const token of ["fixed inset-0", "h-[100dvh]", "desk:max-h-[86vh]", "desk:max-w-5xl", "desk:grid-cols-[1.8fr_1fr]", "minmax(8rem,30vh)", "env(safe-area-inset-bottom)"]) assert.ok(picker.includes(token), token);
});

test("workspace lifecycle separates Close, Cancel edits, and genuine success", () => {
  assert.match(builder, /onClose=\{closeExactWorkspace\}/);
  assert.match(builder, /onCancelEdit=\{editing \? cancelExactEdits : null\}/);
  assert.match(builder, /outcome !== "duplicate" && outcome !== "unchanged"/);
  assert.match(picker, />Cancel edits</);
  assert.match(picker, />Close</);
  assert.match(picker, /onSaveAsNew/);
});

test("focus, scroll lock, search bounds, and artwork fallback are explicit", () => {
  for (const token of ['role="dialog"', 'aria-modal="true"', "FOCUSABLE_SELECTOR", 'event.key === "Escape"', 'document.body.style.overflow = "hidden"', "document.body.style.overflow = previousOverflow", "setTimeout(async () =>", "}, 300)", "controller.abort()", "limit=20", "data-exact-artwork-placeholder", "onError={() => setFailed(true)}"]) assert.ok(picker.includes(token), token);
});

test("Plus execution is separated from browse/select and narrowing remains visible", () => {
  assert.doesNotMatch(picker, /disabled \|\| selected \|\| atMaximum/);
  assert.match(picker, /executionLocked/);
  assert.match(picker, /Requires Index Premium/);
  assert.match(picker, /Additional Builder filters:/);
  assert.match(picker, /Clear narrowing filters/);
});

test("Edit Items restores definition authority and opens the same workspace", () => {
  assert.match(constituents, /data-market-constituents-edit-items/);
  assert.match(constituents, /onEditSeries\?\.\(active\)/);
  assert.match(builder, /builder\.replace\(\{ \.\.\.editingSeries\.spec, exactItems: editingSeries\.exactItems \|\| \[\] \}\)/);
  assert.match(builder, /setExactOpen\(true\)/);
});
