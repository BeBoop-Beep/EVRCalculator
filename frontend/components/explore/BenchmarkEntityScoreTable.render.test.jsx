// Rendered-output (behavioural) tests for the unified Era/Set score table.
import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import BenchmarkEntityScoreTable from "./BenchmarkEntityScoreTable.jsx";
import { mergeScorecardRows } from "./unifiedScoreTableModel.mjs";

const metric = (score, rank, tier, cohortSize = 2) => ({ score, rank, tier, cohortSize });
const publicCard = {
  marketDate: "2026-09-30",
  rows: [
    { entityId: "sv", name: "Scarlet & Violet", modeledSetCount: 16, overall: metric(5.149, 1, "C") },
    { entityId: "mega", name: "Mega Evolution", modeledSetCount: 6, overall: metric(4.602, 2, "D") },
  ],
};
const paidCard = {
  marketDate: "2026-09-30",
  rows: [
    { entityId: "sv", name: "Scarlet & Violet", modeledSetCount: 16, overall: metric(5.149, 1, "C"), financial: metric(5.148, 1, "C"), collector: metric(5.004, 1, "C"), chase: metric(5.26, 1, "S") },
    { entityId: "mega", name: "Mega Evolution", modeledSetCount: 6, overall: metric(4.602, 2, "D"), financial: metric(4.604, 2, "D"), collector: metric(4.989, 2, "C"), chase: metric(4.306, 2, "D") },
  ],
};
const identity = (row) => <span>{row.name}</span>;
const render = (props) => renderToStaticMarkup(<BenchmarkEntityScoreTable entityLabel="Era" showModeledSets renderIdentity={identity} {...props} />);
const TIER = { S: "rgba(192,132,252,0.96)", A: "rgba(45,212,191,0.96)", B: "rgba(134,239,172,0.96)", D: "rgba(251,146,60,0.96)" };

test("entitled Era table renders all four metrics with no dashes for Mega Evolution", () => {
  const html = render({ rows: mergeScorecardRows(publicCard, paidCard).rows, entitled: true, paidStatus: "ready" });
  for (const value of ["4.6", "4.6", "5.0", "4.3", "5.1", "5.3"]) assert.ok(html.includes(`>${value}<`), value);
  assert.ok(html.includes("Modeled Sets"));
  assert.equal((html.match(/data-rankings-unified-score-table/g) || []).length, 1);
  assert.equal((html.match(/<table/g) || []).length, 1);
  const mega = html.slice(html.indexOf('data-entity-id="mega"'), html.indexOf("</tr>", html.indexOf('data-entity-id="mega"')));
  assert.ok(!mega.includes("—"), "Mega Evolution row has no dash cells");
});

test("each cell border uses its OWN tier: Mega Overall D is orange, never purple", () => {
  const html = render({ rows: mergeScorecardRows(publicCard, paidCard).rows, entitled: true, paidStatus: "ready" });
  const mega = html.slice(html.indexOf('data-entity-id="mega"'), html.indexOf("</tr>", html.indexOf('data-entity-id="mega"')));
  assert.ok(mega.includes(TIER.D));
  assert.ok(!mega.includes(TIER.S), "no S/purple border on the below-average Era");
  const sv = html.slice(html.indexOf('data-entity-id="sv"'), html.indexOf("</tr>", html.indexOf('data-entity-id="sv"')));
  assert.ok(sv.includes(TIER.S), "Scarlet & Violet Chase (S) is purple");
  assert.ok(/data-tier="S"/.test(sv) && /data-tier="C"/.test(sv));
});

test("anonymous table: Overall visible, component cells locked, and no component value anywhere in the HTML", () => {
  const leaky = { ...publicCard, rows: publicCard.rows.map((row, i) => ({ ...row, financial: metric(9.111 + i, 1, "S"), collector: metric(9.222 + i, 1, "S"), chase: metric(9.333 + i, 1, "S") })) };
  const html = render({ rows: mergeScorecardRows(leaky, null).rows, entitled: false });
  assert.ok(html.includes(">5.1<") && html.includes(">4.6<"));
  assert.ok((html.match(/data-rankings-locked-cell/g) || []).length >= 6);
  for (const secret of ["9.1", "9.2", "9.3", "10.1", "10.2", "10.3", "data-tier=\"S\""]) assert.ok(!html.includes(secret), secret);
  assert.ok(!html.includes("benchmarkScore"));
  const buttons = [...html.matchAll(/<button[^>]*data-sort-key="(\w+)"[^>]*>/g)];
  const disabled = Object.fromEntries(buttons.map((m) => [m[1], /disabled=""/.test(m[0])]));
  assert.deepEqual(disabled, { overall: false, financial: true, collector: true, chase: true });
});

test("reference row is pinned once, unranked, and neutral", () => {
  const html = render({ rows: mergeScorecardRows(publicCard, paidCard).rows, entitled: true, paidStatus: "ready" });
  assert.equal((html.match(/<tr data-rankings-reference-row/g) || []).length, 1);
  const ref = html.slice(html.indexOf("<tr data-rankings-reference-row"), html.indexOf("</tr>", html.indexOf("<tr data-rankings-reference-row")));
  assert.ok(ref.includes("Pokémon Overall Average"));
  assert.equal((ref.match(/>5\.0</g) || []).length, 4);
  assert.ok(ref.includes("No rank"));
  assert.ok(!/data-tier|#\d/.test(ref));
  assert.ok(!ref.includes("data-rankings-benchmark-component-score"));
});

test("search narrows rows without changing canonical rank or cohort", () => {
  const html = render({ rows: mergeScorecardRows(publicCard, paidCard).rows, query: "mega", entitled: true, paidStatus: "ready" });
  assert.ok(html.includes('data-entity-id="mega"') && !html.includes('data-entity-id="sv"'));
  assert.ok(html.includes("#2"));
  assert.ok(html.includes(" of 2"));
});

test("the visible Rank column starts on the RIP rank and aria-sort marks the active metric", () => {
  const html = render({ rows: mergeScorecardRows(publicCard, paidCard).rows, entitled: true, paidStatus: "ready" });
  assert.ok(html.indexOf('data-entity-id="sv"') < html.indexOf('data-entity-id="mega"'));
  assert.ok(/aria-sort="ascending"[^>]*><button[^>]*data-sort-key="overall"/.test(html));
  assert.equal((html.match(/aria-sort="none"/g) || []).length, 3);
});

test("Set table with an Era filter keeps global canonical ranks", () => {
  const rows = [
    { entityId: "a", name: "Alpha", era: { eraName: "One" }, overall: metric(7, 1, "S", 22) },
    { entityId: "b", name: "Beta", era: { eraName: "Two" }, overall: metric(6, 2, "A", 22) },
    { entityId: "c", name: "Gamma", era: { eraName: "Two" }, overall: metric(4.5, 18, "F", 22) },
  ];
  const html = render({ entityLabel: "Set", showModeledSets: false, rows, eraFilter: "Two", entitled: false });
  assert.ok(!html.includes('data-entity-id="a"'));
  assert.ok(html.includes("#2") && html.includes("#18"));
  assert.ok(!html.includes("#1<"));
});

test("badge strokes use the Rankings palette: S purple, A teal, B green, C sky, D orange, F red (never yellow)", () => {
  const tiers = ["S", "A", "B", "C", "D", "F"];
  const rows = tiers.map((tier, i) => ({ entityId: tier, name: `T${tier}`, overall: metric(5 + i, i + 1, tier, 6) }));
  const html = render({ entityLabel: "Set", showModeledSets: false, rows, entitled: false });
  const strokes = [...html.matchAll(/<polygon[^>]*stroke="([^"]+)"/g)].map((m) => m[1]).slice(0, 6); // desktop table; mobile list repeats it
  assert.deepEqual(strokes, ["rgba(192,132,252,0.96)", "rgba(45,212,191,0.96)", "rgba(134,239,172,0.96)", "rgba(125,211,252,0.96)", "rgba(251,146,60,0.96)", "rgba(248,113,113,0.96)"]);
  assert.ok(!html.includes("253,224,71"));
});
