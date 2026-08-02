const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const source = fs.readFileSync(
  path.resolve(__dirname, "ExploreMarketMovers.jsx"),
  "utf8"
);

test("Explore opts into medium mover thumbnails without changing the shared default", () => {
  assert.ok(source.includes('scope="explore" thumbnailSize="medium"'));
});
