import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "page.js"), "utf8");
const header = fs.readFileSync(path.join(here, "../../components/Header.js"), "utf8");
const footer = fs.readFileSync(path.join(here, "../../components/Footer.jsx"), "utf8");
const rip = fs.readFileSync(path.join(here, "../../components/explore/RipDecisionPage.jsx"), "utf8");

test("Research is a standalone global page, never a set redirect", () => {
  assert.ok(source.includes("export default function ResearchPage()"));
  assert.ok(source.includes(">Research</h1>"));
  assert.ok(!source.includes("redirect("));
  assert.ok(!source.includes("/Explore/rip-statistics"));
});

test("Research documents the canonical public methodology contracts", () => {
  for (const phrase of ["Overall RIP", "Financial RIP", "Collector Appeal", "True Win Frequency", "Typical Retention", "Loss Resilience", "Strong Upside Quality", "Base Economic Efficiency", "Roster desirability", "Desirable outcome frequency", "Dual-path depth", "P50", "P95", "P99", "eligible cohort", "official Pokémon pull rates", "one million", "TCGplayer", "unsupported", "transaction costs"]) {
    assert.ok(source.includes(phrase), phrase);
  }
  assert.ok(!source.includes("RIP Score"));
  assert.ok(!source.includes("Realistic Upside"));
});

test("Research does not disclose production weights or scoring coefficients", () => {
  assert.ok(!/\b\d+(?:\.\d+)?%\s+(?:Financial RIP|Collector Appeal)/.test(source));
  assert.ok(!/\[\"[^\"]+\",\s*\"\d+(?:\.\d+)?%\"/.test(source));
  assert.ok(!source.includes("90% Financial RIP"));
  assert.ok(!source.includes("10% Collector Appeal"));
  assert.ok(!source.includes("weighted formula"));
});

test("global and set-level methodology navigation uses /Research", () => {
  assert.ok(header.includes('href="/Research"'));
  assert.ok(footer.includes('href: "/Research"'));
  assert.ok(rip.includes('methodologyHref = "/Research"'));
});
