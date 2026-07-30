import assert from "node:assert/strict";
import test from "node:test";

import { createMarketDashboardState, marketDashboardReducer } from "./marketDashboardState.mjs";

// ---------------------------------------------------------------------------
// Each Overview module (overview / top-chase / movers) owns one of these
// states. The rules under test:
//   - renderable data always beats a loading status;
//   - a failed or timed-out refresh never erases usable same-set data;
//   - a module with no usable data reaches a real error state (so the section
//     can offer Retry) instead of shimmering forever;
//   - a set switch discards the previous set's data;
//   - each module's state is independent, so one failure cannot blank a
//     sibling section.
// ---------------------------------------------------------------------------

const SET = "ascendedHeroes";
const OTHER_SET = "prismaticEvolutions";

function seeded(setId = SET, payload = { cards: ["seed"] }) {
  return createMarketDashboardState({ status: "success", setId, payload });
}

function idle(setId = SET) {
  return createMarketDashboardState({ status: "idle", setId, payload: null });
}

// --- idle -> loading -> success --------------------------------------------

test("a cold module goes idle -> loading -> success", () => {
  let state = idle();
  assert.equal(state.status, "idle");

  state = marketDashboardReducer(state, { type: "loading", setId: SET });
  assert.equal(state.status, "loading", "with no seeded payload a cold load must show loading");

  state = marketDashboardReducer(state, { type: "success", setId: SET, payload: { cards: ["a"] } });
  assert.equal(state.status, "success");
  assert.deepEqual(state.payload, { cards: ["a"] });
});

// --- idle -> loading -> error -> retry -> success --------------------------

test("a module with no usable data goes idle -> loading -> error -> retry -> success", () => {
  let state = idle();
  state = marketDashboardReducer(state, { type: "loading", setId: SET });
  assert.equal(state.status, "loading");

  state = marketDashboardReducer(state, { type: "error", setId: SET, error: "timed out" });
  assert.equal(state.status, "error", "no renderable data must reach a retryable error state");
  assert.equal(state.error, "timed out");
  assert.equal(state.payload, null, "an error must not invent an empty success payload");

  // Retry
  state = marketDashboardReducer(state, { type: "loading", setId: SET });
  assert.equal(state.status, "loading");

  state = marketDashboardReducer(state, { type: "success", setId: SET, payload: { cards: ["a"] } });
  assert.equal(state.status, "success");
  assert.equal(state.error, null);
});

// --- renderable data beats loading ----------------------------------------

test("same-set seeded data stays visible during a refresh", () => {
  const state = marketDashboardReducer(seeded(), { type: "loading", setId: SET });
  assert.equal(state.status, "success_stale", "a refresh must not replace seeded data with a skeleton");
  assert.deepEqual(state.payload, { cards: ["seed"] });
});

test("a failed refresh does not erase usable same-set data", () => {
  const state = marketDashboardReducer(seeded(), { type: "error", setId: SET, error: "timed out" });
  assert.equal(state.status, "success_stale", "renderable data outranks a failed refresh");
  assert.deepEqual(state.payload, { cards: ["seed"] });
  assert.equal(state.error, "timed out", "the failure is still reported alongside the stale data");
});

test("a reset for the same set keeps already-loaded data", () => {
  const state = marketDashboardReducer(seeded(), { type: "reset", status: "empty", setId: SET });
  assert.equal(state.status, "success_stale");
  assert.deepEqual(state.payload, { cards: ["seed"] });
});

test("repeated refreshes never regress renderable data to loading", () => {
  let state = seeded();
  for (let index = 0; index < 3; index += 1) {
    state = marketDashboardReducer(state, { type: "loading", setId: SET });
    assert.notEqual(state.status, "loading");
    assert.ok(state.payload, "data must remain renderable across every refresh");
  }
});

// --- set switching ---------------------------------------------------------

test("a set switch discards the previous set's payload instead of showing it", () => {
  const state = marketDashboardReducer(seeded(), { type: "loading", setId: OTHER_SET });
  assert.equal(state.status, "loading", "the new set must not render the old set's data");
  assert.equal(state.payload, null);
  assert.equal(state.setId, OTHER_SET);
});

test("a stale response for the previous set cannot overwrite the new set", () => {
  // The effect's isSetStateForActiveSet guard drops the stale response, so the
  // reducer only ever sees the active set. This pins the reducer half: a
  // success for a different set replaces setId wholesale rather than merging.
  let state = marketDashboardReducer(seeded(), { type: "loading", setId: OTHER_SET });
  state = marketDashboardReducer(state, { type: "success", setId: OTHER_SET, payload: { cards: ["new"] } });
  assert.equal(state.setId, OTHER_SET);
  assert.deepEqual(state.payload, { cards: ["new"] });
});

test("an error for a different set does not resurrect the old set's payload", () => {
  let state = marketDashboardReducer(seeded(), { type: "loading", setId: OTHER_SET });
  state = marketDashboardReducer(state, { type: "error", setId: OTHER_SET, error: "boom" });
  assert.equal(state.status, "error");
  assert.equal(state.payload, null);
});

// --- module independence ---------------------------------------------------

test("one module failing does not blank its sibling modules", () => {
  // Three independent states, one dispatch each — the shape the Overview tab
  // uses. A movers failure must leave overview and top-chase untouched.
  const overview = marketDashboardReducer(seeded(SET, { performanceVsCostHistory: [1] }), {
    type: "success",
    setId: SET,
    payload: { performanceVsCostHistory: [1] },
  });
  const topChase = marketDashboardReducer(idle(), {
    type: "success",
    setId: SET,
    payload: { cards: ["chase"] },
  });
  const movers = marketDashboardReducer(idle(), { type: "error", setId: SET, error: "movers timed out" });

  assert.equal(movers.status, "error");
  assert.equal(overview.status, "success", "Opening Profit vs Cost must survive a movers failure");
  assert.deepEqual(overview.payload, { performanceVsCostHistory: [1] });
  assert.equal(topChase.status, "success", "Top Chase must survive a movers failure");
  assert.deepEqual(topChase.payload, { cards: ["chase"] });
});

test("a tab switch mid-request does not strand a module in loading", () => {
  // Leaving the tab dispatches nothing, so the state stays as-is; returning
  // re-dispatches loading and then success. With no seeded payload the module
  // must not be left in a permanent loading state with no way forward — the
  // request-key release in the effect cleanup is what allows this second
  // loading dispatch, and the state machine must accept it.
  let state = marketDashboardReducer(idle(), { type: "loading", setId: SET });
  assert.equal(state.status, "loading");

  // Return to the tab: a fresh request for the same set.
  state = marketDashboardReducer(state, { type: "loading", setId: SET });
  assert.equal(state.status, "loading");

  state = marketDashboardReducer(state, { type: "success", setId: SET, payload: { cards: ["a"] } });
  assert.equal(state.status, "success", "the module must be able to settle after a tab round trip");
});
