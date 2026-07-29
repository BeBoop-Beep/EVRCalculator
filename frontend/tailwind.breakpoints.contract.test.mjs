import test from "node:test";
import assert from "node:assert/strict";

import config from "./tailwind.config.js";

test("the brief's two boundaries exist as named screens", () => {
  const screens = config?.theme?.extend?.screens || {};
  assert.equal(screens.tab, "600px", "tablet layout begins at 600px");
  assert.equal(screens.desk, "1200px", "the untouched desktop layout begins at 1200px");
});

test("the default Tailwind screens are not overridden", () => {
  // Adding screens under `extend` merges; replacing `theme.screens` would
  // silently retune every existing sm/md/lg/xl utility on every page.
  assert.equal(config?.theme?.screens, undefined, "theme.screens must stay unset so defaults survive");
});
