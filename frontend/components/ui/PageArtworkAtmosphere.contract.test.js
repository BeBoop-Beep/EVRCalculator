const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const source = fs.readFileSync(
  path.resolve(__dirname, "PageArtworkAtmosphere.jsx"),
  "utf8"
);

test("page artwork uses the set-page layered atmosphere without affecting layout or input", () => {
  assert.ok(source.includes("set-page-atmosphere pointer-events-none fixed inset-0 -z-10"));
  assert.ok(source.includes("set-page-atmosphere-bloom"));
  assert.ok(source.includes("set-page-atmosphere-artwork"));
  assert.ok(source.includes('loading = "eager"'));
  assert.equal((source.match(/loading=\{loading\}/g) || []).length, 2);
  assert.equal((source.match(/object-contain object-center/g) || []).length, 2);
  assert.ok(source.includes("if (!src)"));
});

test("the shared artwork component leaves presentation tuning to scoped CSS variables", () => {
  const globals = fs.readFileSync(
    path.resolve(__dirname, "../../app/styles/globals.css"),
    "utf8"
  );
  assert.ok(globals.includes("scale(var(--set-artwork-scale))"));
  const exploreTuning = globals.slice(
    globals.indexOf(".explore-glass-scope .set-page-atmosphere {"),
    globals.indexOf(".explore-glass-scope .set-page-atmosphere {") + 760
  );
  assert.ok(exploreTuning.includes("--set-artwork-scale: 1.02"));
  assert.ok(exploreTuning.includes("--set-artwork-opacity: 0.09945"));
  assert.ok(exploreTuning.includes("--set-artwork-bloom-opacity: 0.0459"));
  assert.ok(exploreTuning.includes("--set-artwork-bloom-scale: 1.037"));
  assert.ok(exploreTuning.includes("--set-artwork-bloom-brightness: 0.918"));
  assert.ok(exploreTuning.includes("--set-artwork-mask:"));
  assert.ok(globals.includes("object-position: center 38%"));
  assert.ok(!globals.includes(".explore-glass-scope [data-explore-ambient-artwork]"));
});
