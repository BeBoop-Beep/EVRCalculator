import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const collector = read("./CardCollectorAppealRankings.jsx");
const chase = read("./CardChaseEfficiencyRankings.jsx");
const filters = read("./CardRankingsFilterBar.jsx");
const hub = read("./CardRankingsHub.jsx");
const proxy = read("../../app/api/explore/card-ranking-facets/route.js");

test("Collector exposes the five component lenses without cosmetic re-ranking", () => {
  for (const label of ["Overall", "Pokémon", "Trainer", "Artist", "Playability"]) assert.ok(collector.includes(`label: "${label}"`));
  for (const lens of ["overall", "pokemon", "trainer", "artist", "playability"]) assert.ok(collector.includes(`value: "${lens}"`));
  assert.match(collector, /#\{row\.rank\}/);
  assert.doesNotMatch(collector, /rows\.(sort|filter)\(/);
  assert.doesNotMatch(collector, /RankingsRipScoreBadge|RipScoreBadge|\/10/);
  assert.match(collector, /toFixed\(1\)/);
});

test("Cards use one shared real-facet filter surface", () => {
  assert.match(collector, /<CardRankingsFilterBar/);
  assert.match(chase, /<CardRankingsFilterBar/);
  assert.match(filters, /MultiSelectFilter/);
  for (const label of ['entity="Cards"', "Search Eras…", "Search Sets…", "Search Rarities…", "Clear filters"]) assert.ok(filters.includes(label), label);
  assert.doesNotMatch(filters, /<select/);
  assert.doesNotMatch(hub, /targets=/);
});

test("facet and row reads remain lazy, separately keyed, and entitlement guarded", () => {
  assert.match(collector, /!entitled/);
  assert.match(chase, /!entitled/);
  assert.match(collector, /cards:facets:collector/);
  assert.match(chase, /cards:facets:chase/);
  assert.match(collector, /collector:\$\{lens\}/);
  assert.match(collector, /results\[lens\]/);
});

test("facet proxy preserves the paid read boundary", () => {
  assert.match(proxy, /card-ranking-facets/);
  assert.match(proxy, /headers\.Authorization = authorization/);
  assert.match(proxy, /headers\.Cookie = cookie/);
  assert.match(proxy, /cache: "no-store"/);
  assert.match(proxy, /status: response\.status/);
  assert.match(proxy, /private, no-store/);
  assert.match(proxy, /Cookie, Authorization/);
});
