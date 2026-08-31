import assert from "node:assert/strict";
import test from "node:test";
import { clearPokemonSetRipBootstrapCache, getPokemonSetRipBootstrap, seedPokemonSetRipBootstrap, SET_RIP_BOOTSTRAP_CACHE_LIMIT, SET_RIP_BOOTSTRAP_TTL_MS } from "./pokemonSetRipBootstrapClient.mjs";

const raw = (id) => ({ contractVersion: "pokemon-set-rip-bootstrap-v1", set: { id }, canonicalRip: {}, summary: {} });
const normalized = (id) => ({ available: true, set: { id } });

test("server bootstrap seeds suppress an identical browser request", async () => {
  clearPokemonSetRipBootstrapCache(); let calls = 0; global.fetch = async () => { calls += 1; return { ok: true, json: async () => raw("set-a") }; };
  seedPokemonSetRipBootstrap("set-a", normalized("set-a"));
  assert.equal((await getPokemonSetRipBootstrap("set-a")).set.id, "set-a");
  assert.equal(calls, 0);
});

test("identical in-flight requests dedupe and completed results stay bounded", async () => {
  clearPokemonSetRipBootstrapCache(); let calls = 0; global.fetch = async (url) => { calls += 1; const id = decodeURIComponent(String(url).split("/sets/")[1].split("/")[0]); return { ok: true, json: async () => raw(id) }; };
  const [a, b] = await Promise.all([getPokemonSetRipBootstrap("set-a"), getPokemonSetRipBootstrap("set-a")]);
  assert.equal(a, b); assert.equal(calls, 1);
  for (let index = 0; index < SET_RIP_BOOTSTRAP_CACHE_LIMIT + 2; index += 1) await getPokemonSetRipBootstrap(`set-${index}`);
  assert.equal(SET_RIP_BOOTSTRAP_TTL_MS, 300000);
});

test("wrong-set bootstrap responses are rejected and never cached", async () => {
  clearPokemonSetRipBootstrapCache(); let calls = 0; global.fetch = async () => { calls += 1; return { ok: true, json: async () => raw("set-b") }; };
  await assert.rejects(getPokemonSetRipBootstrap("set-a"), /identity/);
  await assert.rejects(getPokemonSetRipBootstrap("set-a"), /identity/);
  assert.equal(calls, 2);
});
