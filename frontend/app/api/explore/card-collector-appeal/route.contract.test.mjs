import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("Collector Appeal proxy forwards auth and remains private no-store", () => {
  assert.match(source, /\/explore\/card-collector-appeal/);
  assert.match(source, /headers\.Authorization = authorization/);
  assert.match(source, /headers\.Cookie = cookie/);
  assert.match(source, /cache: "no-store"/);
  assert.match(source, /private, no-store/);
});
