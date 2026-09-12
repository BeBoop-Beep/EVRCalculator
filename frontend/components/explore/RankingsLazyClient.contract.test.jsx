import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "RankingsLazyClient.jsx"), "utf8").replace(/\r\n/g, "\n");

test("passes the real entitlement flag into the Set hub", () => {
  assert.match(source, /<SetRankingsHub[^>]*canViewRankingsIntelligence=\{canViewRankingsIntelligence\}/);
  assert.doesNotMatch(source, /<SetRankingsHub[^>]*canViewRankingsIntelligence\s+(?:eraFilter|\/>)/);
});
