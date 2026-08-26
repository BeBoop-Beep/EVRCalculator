// The builder's canonical-filter load: one distinguishable state per cause.
//
// THE DEFECT. The builder read `payload?.message` and fell back to "Unable to
// load query filters". FastAPI answers 401 with `detail`, not `message`, so a
// signed-out user — the ordinary case — was told the filters were broken. The
// transport was never at fault: the app's session is an HttpOnly `token`
// cookie, the same-origin proxy forwards it, and the backend reads it through
// the same `_extract_token` path `/auth/me` uses.
//
// So these tests pin CAUSE SEPARATION, not a happy path.

import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerQueryBuilder, {
  OPTIONS_STATUS,
  backendMessage,
  resolveOptionsStatus,
} from "./MarketExplorerQueryBuilder.jsx";
import { __resetMarketExplorerFilterOptionsCache } from "@/hooks/explore/useMarketExplorerFilterOptions";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS_PAYLOAD = {
  asset: { id: "cards", label: "Cards" },
  eras: [{ id: "era-sv", label: "Scarlet & Violet", sortOrder: 3 }],
  sets: [{ id: "set-ah", label: "Ascended Heroes", eraId: "era-sv" }],
  segments: { segments: [{ key: "special_illustration_rare", label: "Special Illustration Rare" }] },
};

async function mountWith(responder) {
  // The canonical options payload is cached per page load, so each test must
  // start from a cold cache or it would assert against the previous fixture.
  __resetMarketExplorerFilterOptionsCache();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = responder;
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(<MarketExplorerQueryBuilder onAddQuery={async () => "added"} />);
  });
  globalThis.fetch = originalFetch;
  return renderer;
}

const stateNode = (renderer) =>
  renderer.root.findAll((node) => node.props?.["data-market-query-options-state"] !== undefined)[0] || null;
const stateOf = (renderer) => stateNode(renderer)?.props["data-market-query-options-state"] || null;

test("an HTTP status maps to the state the user can act on", () => {
  assert.equal(resolveOptionsStatus(401), OPTIONS_STATUS.signedOut);
  assert.equal(resolveOptionsStatus(403), OPTIONS_STATUS.signedOut);
  assert.equal(resolveOptionsStatus(404), OPTIONS_STATUS.unavailable);
  assert.equal(resolveOptionsStatus(500), OPTIONS_STATUS.unavailable);
  assert.equal(resolveOptionsStatus(503), OPTIONS_STATUS.unavailable);
});

test("both error shapes are read: FastAPI detail and the app's own message", () => {
  assert.equal(backendMessage({ detail: "Not authenticated" }), "Not authenticated");
  assert.equal(backendMessage({ message: "no tracked sets" }), "no tracked sets");
  assert.equal(backendMessage(null), "");
  assert.equal(backendMessage({ detail: { loc: ["body"] } }), "", "a non-string detail is not a message");
});

test("a signed-out user is asked to sign in, not told the filters are broken", async () => {
  const renderer = await mountWith(async () => ({
    ok: false, status: 401, json: async () => ({ detail: "Not authenticated" }),
  }));
  assert.equal(stateOf(renderer), OPTIONS_STATUS.signedOut);
  const rendered = JSON.stringify(renderer.toJSON());
  // The copy names the ACCOUNT step only. It deliberately no longer says
  // signing in gets you a custom market: the builder is Index Premium, and
  // login alone unlocks nothing.
  assert.ok(rendered.includes("Sign in to continue."));
  assert.ok(rendered.includes("Index Premium"),
    "the real requirement must be stated, not implied by a sign-in button");
  assert.ok(!rendered.includes("Sign in to build a custom market."),
    "copy that promised login was enough must not come back");
  assert.ok(!rendered.includes("Unable to load query filters"),
    "the string that hid every cause must not come back");
  const link = renderer.root.findAll((node) => node.props?.["data-market-query-sign-in"] !== undefined)[0];
  assert.ok(link, "the sign-in state must offer the canonical login route");
  assert.equal(link.props.href, "/login");
});

test("a service failure is reported as a service failure", async () => {
  const renderer = await mountWith(async () => ({
    ok: false, status: 503, json: async () => ({ message: "no tracked sets have market history" }),
  }));
  assert.equal(stateOf(renderer), OPTIONS_STATUS.unavailable);
  const rendered = JSON.stringify(renderer.toJSON());
  assert.ok(rendered.includes("temporarily unavailable"));
  assert.ok(rendered.includes("no tracked sets have market history"),
    "the backend's own reason is carried through rather than discarded");
});

test("a transport failure is never reported as an auth answer", async () => {
  const renderer = await mountWith(async () => { throw new TypeError("fetch failed"); });
  assert.equal(stateOf(renderer), OPTIONS_STATUS.offline);
  assert.ok(!JSON.stringify(renderer.toJSON()).includes("Sign in"),
    "a dead backend must not be presented as being signed out");
});

test("an authenticated session renders the builder, not a state message", async () => {
  const renderer = await mountWith(async () => ({ ok: true, status: 200, json: async () => OPTIONS_PAYLOAD }));
  assert.equal(stateOf(renderer), null, "no error state survives a successful load");
  assert.ok(renderer.root.findAll((node) => node.props?.["data-multi-select-trigger"] === "era").length === 1);
});

test("the options request travels on the ordinary same-origin session", async () => {
  const calls = [];
  await mountWith(async (url, init) => {
    calls.push({ url, init });
    return { ok: true, status: 200, json: async () => OPTIONS_PAYLOAD };
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/market/explorer/query",
    "same-origin, so the HttpOnly token cookie is attached by the browser");
  assert.equal(calls[0].init.credentials, "include");
  assert.ok(!calls[0].init?.headers?.Authorization,
    "no developer-only header injection: the normal session is the only credential");
});
