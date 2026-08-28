import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(new URL("../../app/TCGs/Pokemon/Sets/[setSlug]/page.js", import.meta.url), "utf8");

test("RIP and Market directory technical failure propagates instead of fabricating empty targets", () => {
  const bodyStart = page.indexOf("export default async function TcgSetRipStatisticsPage");
  const body = page.slice(bodyStart);
  assert.match(body, /useSlimSetDirectory\s*\? await getPokemonSetRouteDirectory/);
  assert.doesNotMatch(body, /getPokemonSetRouteDirectory\(\{ limit: 150 \}\)\.catch/);
  assert.match(body, /: await getRipStatisticsTargets\(\{ limit: 150 \}\)\.catch/);
});

test("notFound runs only after a successfully obtained authoritative target list", () => {
  const fetchIndex = page.indexOf("const targetsPayload = useSlimSetDirectory");
  const selectedIndex = page.indexOf("const selectedTarget = findTargetBySetSlug", fetchIndex);
  const notFoundIndex = page.indexOf("if (!selectedTarget) notFound()", selectedIndex);
  assert.ok(fetchIndex >= 0 && selectedIndex > fetchIndex && notFoundIndex > selectedIndex);
});

test("metadata retains its generic fallback when directory lookup fails", () => {
  const metadata = page.slice(page.indexOf("export async function generateMetadata"), page.indexOf("export default async function"));
  assert.match(metadata, /getPokemonSetRouteDirectory[\s\S]*\.catch\([\s\S]*=> null/);
});
