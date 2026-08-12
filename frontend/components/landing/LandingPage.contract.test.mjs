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

test("hero has exact answer, locked metrics, local pack image, and neutral fallback", () => {
  for (const label of ["BEST SET TO RIP RIGHT NOW", "Overall RIP", "Financial RIP", "Expected Value", "Typical Opening"]) assert.match(component, new RegExp(label));
  assert.match(component, /boosterPackImage\.src/);
  assert.match(component, /<SetMark set=\{set\} className=\{styles\.heroLogo\}/);
  assert.doesNotMatch(component, /Local pack image unavailable/);
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

test("phone hero keeps the complete decision snapshot compact above the fixed navigation", () => {
  const phone = css.slice(css.indexOf("@media(max-width:560px)"), css.indexOf("@media(prefers-reduced-motion:reduce)"));
  assert.match(phone, /\.heroShell\{padding:14px 0 24px\}/);
  assert.match(phone, /\.hero h1\{font-size:39px;line-height:\.94;margin:8px 0 12px\}/);
  assert.match(phone, /\.theater\{height:178px;margin-top:0\}/);
  assert.match(phone, /\.metricGrid\{gap:6px;margin:8px 0 16px\}/);
  assert.match(phone, /\.metricGrid div\{min-height:64px;padding:9px 10px\}/);
});

test("simulation proof reuses the Insights distribution with canonical landmarks", () => {
  assert.match(component, /<DistributionVisual distribution=\{distribution\}/);
  assert.match(component, /import RipDistributionChart from "@\/components\/explore\/RipDistributionChart"/);
  assert.match(component, /<RipDistributionChart/);
  assert.match(component, /thresholdBins=\{distribution\.thresholdBins\}/);
  const visual = component.slice(component.indexOf("function DistributionVisual"), component.indexOf("export default function"));
  assert.doesNotMatch(visual, /<svg|<rect|<line|<canvas|monotone|interpolat|bell curve/i);
});

test("live number two and three cards use dynamic imagery around a centered foreground product", () => {
  assert.match(component, /rows\.slice\(1, 3\)/);
  assert.match(component, /className=\{styles\.supportLockup\}/);
  assert.match(component, /<SupportingSetVisual row=\{row\}[\s\S]*className=\{styles\.supportRank\}>#\{row\.rank\}<\/span>/);
  assert.doesNotMatch(component, /row\.boosterPackImage/);
  assert.match(component, /<SetMark set=\{row\} className=\{styles\.supportLogo\}/);
  assert.match(css, /\.rankPlane\{position:absolute;z-index:1/);
  assert.match(css, /\.productStage\{position:absolute;z-index:2/);
  assert.match(css, /\.supportVisual\{position:relative;[^}]*overflow:hidden/);
  assert.match(css, /\.supportLogo\{position:absolute;inset:0;[^}]*object-fit:contain/);
  assert.match(css, /\.supportLockup\{display:flex;align-items:center;justify-content:flex-end;gap:10px/);
  const phone = css.slice(css.indexOf("@media(max-width:560px)"), css.indexOf("@media(prefers-reduced-motion:reduce)"));
  assert.match(phone, /\.productStage\{inset:0;width:68%;margin-inline:auto\}/);
  assert.match(phone, /\.supportLockup\{gap:7px;padding:4px 6px\}/);
  assert.match(phone, /\.rankTwo \.supportLockup\{justify-content:flex-start\}/);
  assert.match(phone, /\.rankThree \.supportLockup\{justify-content:flex-end\}/);
  assert.match(phone, /\.rankTwo\{left:0;right:auto/);
  assert.match(phone, /\.rankThree\{left:auto;right:0/);
});

test("both full-ranking links use the canonical Rankings route", () => {
  assert.equal((component.match(/href="\/Rankings"/g) || []).length, 2);
  assert.doesNotMatch(component, /See Full Rankings[\s\S]{0,120}\/Explore\/rip-statistics/);
});
