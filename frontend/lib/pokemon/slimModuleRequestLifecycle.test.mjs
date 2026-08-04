import assert from "node:assert/strict";
import test, { mock } from "node:test";
import { createRequire } from "node:module";

// See slimModuleNormalizationReliability.test.mjs — createRequire is the import
// form that resolves this CJS-transpiled ESM module under the suite's tsx runner.
const require = createRequire(import.meta.url);
const {
  __hasSlimModuleInflightForTests,
  __getSlimModuleInflightSizeForTests,
  getPokemonSetMarketMovers,
  getPokemonSetOverview,
  getPokemonSetTopChase,
} = require("./pokemonSetMarketClient.js");

// ---------------------------------------------------------------------------
// Bounded completion policy for the slim Overview module fetches.
//
// Before this policy existed, these fetches had no timeout of any kind. A
// request that never produced a response left the section's Promise
// permanently unsettled, which meant:
//   - the section stayed on its loading skeleton forever, and
//   - the key stayed in slimModuleInflight (deleted only in .finally()), so
//     every later visit and every Retry joined the same dead Promise instead
//     of issuing a new request.
//
// These tests assert the request always settles, always releases its key, and
// that a retry therefore issues a genuinely new request.
// ---------------------------------------------------------------------------

const TIMEOUT_MS = 20_000;

function stubNeverResolvingFetch() {
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = () => {
    callCount += 1;
    // Never settles, and never rejects on abort either — the worst case the
    // client-side bound exists to cover.
    return new Promise(() => {});
  };
  return {
    getCallCount: () => callCount,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

function stubOkFetch(body) {
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: true, status: 200, json: async () => body };
  };
  return {
    getCallCount: () => callCount,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

function stubFailingFetch(status, body) {
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return { ok: false, status, json: async () => body };
  };
  return {
    getCallCount: () => callCount,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

// Top Chase makes up to TWO attempts, and each attempt owns its own
// AbortController + timeout (a single shared controller would leave attempt two
// with an already-aborted signal). Driving it to completion under mock timers
// therefore needs the clock advanced past attempt one's timeout, the retry
// delay, and attempt two's timeout — with microtasks flushed in between.
// It must stop advancing as soon as the operation settles: a blind tick loop
// would fire attempt two's own timeout before its (already resolved) fetch had
// finished working through its microtasks, turning a success into a timeout.
async function flushMicrotasks(count = 25) {
  for (let i = 0; i < count; i += 1) {
    await Promise.resolve();
  }
}

async function advanceThroughBothTopChaseAttempts(settled, steps = 6) {
  let done = false;
  const tracked = settled.then((value) => {
    done = true;
    return value;
  });

  for (let step = 0; step < steps && !done; step += 1) {
    await flushMicrotasks();
    if (done) {
      break;
    }
    mock.timers.tick(TIMEOUT_MS);
  }

  await flushMicrotasks();
  return tracked;
}

test("an unresolved request eventually settles as a retryable timeout instead of loading forever", async () => {
  const stub = stubNeverResolvingFetch();
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const pending = getPokemonSetTopChase("timeout-set", { window: "365d", limit: 10 });
    const settled = pending.then(
      () => ({ ok: true }),
      (error) => ({ ok: false, error })
    );

    const result = await advanceThroughBothTopChaseAttempts(settled);

    assert.equal(result.ok, false, "a request that never responds must reject, not hang");
    assert.equal(result.error.code, "SLIM_MODULE_REQUEST_TIMEOUT");
    assert.equal(result.error.status, 504);
    assert.equal(result.error.retryable, true);
    assert.equal(result.error.isTimeout, true);
  } finally {
    mock.timers.reset();
    stub.restore();
  }
});

test("a timed-out request releases its shared in-flight key", async () => {
  const stub = stubNeverResolvingFetch();
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const key = "movers:release-set:7D:10:all";
    const pending = getPokemonSetMarketMovers("release-set", { window: "7D", limit: 10 });
    const settled = pending.catch((error) => error);

    assert.ok(__hasSlimModuleInflightForTests(key), "the in-flight key must be registered while the request runs");

    mock.timers.tick(TIMEOUT_MS);
    await settled;

    assert.ok(
      !__hasSlimModuleInflightForTests(key),
      "a timeout must release the key so a retry cannot join the dead request"
    );
  } finally {
    mock.timers.reset();
    stub.restore();
  }
});

test("a retry after a timeout starts exactly one fresh request", async () => {
  const timedOut = stubNeverResolvingFetch();
  mock.timers.enable({ apis: ["setTimeout"] });
  let firstCallCount = 0;
  try {
    const settled = getPokemonSetOverview("retry-set", { window: "365d" }).catch((error) => error);
    mock.timers.tick(TIMEOUT_MS);
    await settled;
    firstCallCount = timedOut.getCallCount();
  } finally {
    mock.timers.reset();
    timedOut.restore();
  }
  assert.equal(firstCallCount, 1);

  // The retry runs against a healthy backend and must actually hit the
  // network rather than resolving from the poisoned in-flight entry.
  const healthy = stubOkFetch({ set: { id: "retry-set" }, performanceVsCostHistory: [] });
  try {
    const payload = await getPokemonSetOverview("retry-set", { window: "365d" });
    assert.equal(healthy.getCallCount(), 1, "the retry must issue exactly one new request");
    assert.equal(payload.set.id, "retry-set");
  } finally {
    healthy.restore();
  }
});

test("a successful request releases its in-flight key", async () => {
  const stub = stubOkFetch({ set: { id: "ok-set" }, topChaseCards: [] });
  try {
    await getPokemonSetTopChase("ok-set", { window: "365d", limit: 10 });
    assert.ok(!__hasSlimModuleInflightForTests("top-chase:ok-set:365d:10"));
    assert.equal(__getSlimModuleInflightSizeForTests(), 0);
  } finally {
    stub.restore();
  }
});

test("a failed request releases its in-flight key so the section can retry", async () => {
  const stub = stubFailingFetch(504, { message: "movers request timed out", code: "POKEMON_SET_MARKET_MOVERS_PROXY_TIMEOUT" });
  try {
    await assert.rejects(
      () => getPokemonSetMarketMovers("fail-set", { window: "7D", limit: 10 }),
      /timed out/i
    );
    assert.ok(!__hasSlimModuleInflightForTests("movers:fail-set:7D:10:all"));
  } finally {
    stub.restore();
  }

  const healthy = stubOkFetch({ set: { id: "fail-set" }, marketMovers: { all: [], heatingUp: [], coolingOff: [] } });
  try {
    await getPokemonSetMarketMovers("fail-set", { window: "7D", limit: 10 });
    assert.equal(healthy.getCallCount(), 1, "a retry after a proxy failure must issue a new request");
  } finally {
    healthy.restore();
  }
});

test("the proxy's structured timeout body surfaces as the section's error message", async () => {
  // The Next proxy answers a stalled backend with a structured, retryable 504
  // (see slimSetModuleProxyContract.mjs). readJsonResponse must surface that
  // message so the section renders a real reason next to its Retry button.
  const stub = stubFailingFetch(504, {
    message: "set market movers request timed out",
    code: "POKEMON_SET_MARKET_MOVERS_PROXY_TIMEOUT",
    retryable: true,
  });
  try {
    await assert.rejects(
      () => getPokemonSetMarketMovers("proxy-timeout-set", { window: "7D", limit: 10 }),
      (error) => {
        assert.equal(error.status, 504);
        assert.match(error.message, /timed out/i);
        return true;
      }
    );
  } finally {
    stub.restore();
  }
});

test("StrictMode's duplicate effect invocation still joins one request", async () => {
  const stub = stubOkFetch({ set: { id: "strict-set" }, topChaseCards: [] });
  try {
    const [first, second] = await Promise.all([
      getPokemonSetTopChase("strict-set", { window: "365d", limit: 10 }),
      getPokemonSetTopChase("strict-set", { window: "365d", limit: 10 }),
    ]);
    assert.equal(stub.getCallCount(), 1, "duplicate concurrent effects must share one network request");
    assert.deepEqual(first, second);
  } finally {
    stub.restore();
  }
});

test("a slow-but-successful request is never pre-empted into an error", async () => {
  // The client bound must sit above the proxy's own timeout so an ordinary
  // slow read still completes as a success.
  const originalFetch = globalThis.fetch;
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    globalThis.fetch = () =>
      new Promise((resolve) => {
        setTimeout(() => resolve({ ok: true, status: 200, json: async () => ({ set: { id: "slow-set" } }) }), 15_000);
      });

    const pending = getPokemonSetOverview("slow-set", { window: "365d" });
    // joinSlimModuleRequest invokes the factory in a microtask, so the stub's
    // own timer is not registered yet. Flush microtasks before advancing time,
    // otherwise the tick fires against an empty timer queue and the request
    // never resolves.
    await Promise.resolve();
    await Promise.resolve();
    mock.timers.tick(15_000);
    const payload = await pending;
    assert.equal(payload.set.id, "slow-set", "a 15s success must still be a success");
  } finally {
    mock.timers.reset();
    globalThis.fetch = originalFetch;
  }
});

test("a timed-out Top Chase attempt is retried with a fresh, non-aborted signal", async () => {
  // The defect this pins: joinSlimModuleRequest created ONE AbortController for
  // the whole joined operation. When its timeout fired it aborted that
  // controller, so attempt two started from an already-aborted signal and could
  // never succeed. Each attempt must now own its controller.
  const originalFetch = globalThis.fetch;
  const observedSignals = [];
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    globalThis.fetch = (_url, init = {}) => {
      observedSignals.push(init.signal);
      if (observedSignals.length === 1) {
        // Attempt one never responds, so its own timeout aborts it.
        return new Promise(() => {});
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          set: { id: "retry-signal-set" },
          topChaseCards: [
            {
              cardVariantId: "v0",
              marketPrice: 12,
              priceHistory: [
                { date: "2026-08-02", marketPrice: 11 },
                { date: "2026-08-03", marketPrice: 12 },
              ],
            },
          ],
          latestMarketDate: "2026-08-03",
        }),
      });
    };

    const pending = getPokemonSetTopChase("retry-signal-set", { window: "365d", limit: 10 });
    const settled = pending.then(
      (payload) => ({ ok: true, payload }),
      (error) => ({ ok: false, error })
    );

    const result = await advanceThroughBothTopChaseAttempts(settled);

    assert.equal(result.ok, true, "attempt two must be able to succeed after attempt one timed out");
    assert.equal(result.payload.topChaseVerdict.status, "complete");

    assert.equal(observedSignals.length, 2, "exactly two attempts, no more");
    assert.notEqual(observedSignals[0], observedSignals[1], "each attempt needs its OWN controller");
    assert.equal(observedSignals[0].aborted, true, "attempt one's signal was aborted by its own timeout");
    assert.equal(observedSignals[1].aborted, false, "attempt two must start from a fresh, non-aborted signal");

    // The shared identity key is still released after the final outcome.
    assert.ok(!__hasSlimModuleInflightForTests("top-chase:retry-signal-set:365d:10"));
    assert.equal(__getSlimModuleInflightSizeForTests(), 0);
  } finally {
    mock.timers.reset();
    globalThis.fetch = originalFetch;
  }
});

test("a non-retryable 4xx Top Chase response does not spend a second attempt", async () => {
  const stub = stubFailingFetch(404, { message: "set not found", code: "POKEMON_SET_NOT_FOUND" });
  try {
    await assert.rejects(() => getPokemonSetTopChase("missing-set", { window: "365d", limit: 10 }));
    assert.equal(stub.getCallCount(), 1, "a 4xx is settled; retrying it only burns a request");
    assert.ok(!__hasSlimModuleInflightForTests("top-chase:missing-set:365d:10"));
  } finally {
    stub.restore();
  }
});
