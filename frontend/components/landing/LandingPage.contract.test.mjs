import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(join(here, path), "utf8");
const page = read("../../app/page.js");
const component = read("./RankingTheaterHomepage.jsx");
const css = read("./rankingTheater.module.css");
const server = read("../../lib/landing/landingHeroServer.js");

test("the locked homepage story renders in order", () => {
  const phrases = ["WHAT&rsquo;S ACTUALLY", "BEST SETS TO RIP RIGHT NOW", "What does one million simulated openings actually look like?", "Your best set might be different."];
  let cursor = -1;
  for (const phrase of phrases) { const next = component.indexOf(phrase); assert.ok(next > cursor, phrase); cursor = next; }
});

test("one payload drives the dynamic winner and includes rank one in the board", () => {
  assert.match(server, /getRipStatisticsTargets/);
  assert.match(server, /openingSpotlightSet = entries\[0\]/);
  assert.match(server, /selectExploreRankingRows\(entries/);
  assert.doesNotMatch(server, /slice\(1/);
  assert.match(page, /set=\{openingSpotlightSet\}/);
});

test("hero has exact answer, locked metrics, local image, and intentional fallback", () => {
  for (const label of ["BEST SET TO RIP RIGHT NOW", "Overall RIP", "Financial RIP", "Expected Value", "Typical Opening"]) assert.match(component, new RegExp(label));
  assert.match(component, /boosterPackImage\.src/);
  assert.match(component, /Local pack image unavailable/);
  assert.doesNotMatch(component, /https?:\/\/.*booster/i);
});

test("personalization uses the waitlist because no Personal RIP route exists", () => {
  assert.match(component, /Join the Personal RIP beta/);
  assert.doesNotMatch(component, /href=["']\/.*personal/i);
});

test("mobile is recomposed, has no horizontal dependency, and reduced motion resolves immediately", () => {
  assert.match(css, /\.mobileTheater\{display:block/);
  assert.match(css, /grid-template-columns:repeat\(2,1fr\)/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/);
  assert.doesNotMatch(css, /overflow-x:auto/);
});
