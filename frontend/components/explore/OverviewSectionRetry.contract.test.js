const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const clientPath = path.resolve(__dirname, "RipStatisticsPageClient.jsx");
// This file mixes CRLF and LF; normalize before any multi-line anchoring.
const source = fs.readFileSync(clientPath, "utf8").replace(/\r\n/g, "\n");

const section = (startToken, endToken) => {
  const start = source.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = source.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return source.slice(start, end);
};

// ---------------------------------------------------------------------------
// Each of the three slim Overview modules must be independently retryable
// without a page reload and without restarting its siblings.
// ---------------------------------------------------------------------------

test("each slim Overview module has its own retry callback", () => {
  for (const [callback, ref] of [
    ["retryOverviewModule", "lastOverviewRequestKeyRef"],
    ["retryTopChaseModule", "lastTopChaseRequestKeyRef"],
    ["retryMarketMoversModule", "lastMarketMoversRequestKeyRef"],
  ]) {
    const body = section(`const ${callback} = useCallback(() => {`, "}, []);");
    assert.ok(
      body.includes(`${ref}.current = null`),
      `${callback} must release its request-key guard so the refetch is not skipped as a duplicate`
    );
  }
});

test("a retry re-runs only its own module effect", () => {
  // Separate nonces, one per effect dependency array: retrying movers must not
  // re-run the overview or top-chase effects.
  for (const nonce of ["overviewRetryNonce", "topChaseRetryNonce", "marketMoversRetryNonce"]) {
    assert.ok(source.includes(`const [${nonce}, set`), `${nonce} must be module-local state`);
  }

  const overviewDeps = section("if (!requestSettled && lastOverviewRequestKeyRef.current === overviewRequestKey)", "]);");
  assert.ok(overviewDeps.includes("overviewRetryNonce"), "the overview effect must depend on its own nonce");
  assert.ok(!overviewDeps.includes("topChaseRetryNonce"), "the overview effect must not depend on a sibling's nonce");
  assert.ok(!overviewDeps.includes("marketMoversRetryNonce"), "the overview effect must not depend on a sibling's nonce");

  const topChaseDeps = section("if (!requestSettled && lastTopChaseRequestKeyRef.current === topChaseRequestKey)", "]);");
  assert.ok(topChaseDeps.includes("topChaseRetryNonce"));
  assert.ok(!topChaseDeps.includes("overviewRetryNonce"));
  assert.ok(!topChaseDeps.includes("marketMoversRetryNonce"));

  const moversDeps = section(
    "if (!requestSettled && lastMarketMoversRequestKeyRef.current === marketMoversRequestKey)",
    "]);"
  );
  assert.ok(moversDeps.includes("marketMoversRetryNonce"));
  assert.ok(!moversDeps.includes("overviewRetryNonce"));
  assert.ok(!moversDeps.includes("topChaseRetryNonce"));
});

test("all three Overview sections expose their retry to the user", () => {
  assert.ok(
    source.includes("onRetry={retryMarketMoversModule}"),
    "the 7D Movers ticker must offer a section-local Retry"
  );
  assert.ok(
    source.includes("onRetry={retryTopChaseModule}"),
    "Top Chase Cards must offer a section-local Retry"
  );
  assert.ok(
    source.includes("onRetry={retryOverviewModule}"),
    "Opening Profit vs Cost must offer a section-local Retry"
  );
});

test("the movers ticker renders a retryable error instead of an endless pulse", () => {
  const ticker = section("function MarketMoversTicker(", "function normalizePullRateAssumptions");
  assert.ok(ticker.includes("onRetry"), "the ticker must accept a retry handler");
  // The error branch, not the loading branch, is what carries Retry.
  const errorBranch = ticker.slice(ticker.indexOf('status === "error"'));
  assert.ok(errorBranch.includes("Retry"), "the error state must offer Retry");
});

test("Top Chase renders a retryable error state", () => {
  const content = section("function TopMarketCardsContent(", "function TopChaseCardsModule");
  const errorBranch = content.slice(content.indexOf('if (status === "error")'));
  assert.ok(errorBranch.includes("onRetry"), "the Top Chase error state must offer Retry");
});

test("Top Chase keeps a five-row default with all ten rows reachable", () => {
  const chaseModule = section("function TopChaseCardsModule(", "function normalizePullRateAssumptions");
  assert.ok(chaseModule.includes("showAllChaseCards ? 10 : TOP_CHASE_MOBILE_PREVIEW_LIMIT"), "five rows by default, ten on expand");
});

test("retrying a section never shows the global page loader", () => {
  for (const callback of ["retryOverviewModule", "retryTopChaseModule", "retryMarketMoversModule"]) {
    const body = section(`const ${callback} = useCallback(() => {`, "}, []);");
    assert.ok(!body.includes("setIsLoading"), `${callback} must not trigger a page-level loader`);
    assert.ok(!body.includes("startTransition"), `${callback} must not trigger a route transition`);
  }
});

test("nothing retries automatically in a loop", () => {
  for (const callback of ["retryOverviewModule", "retryTopChaseModule", "retryMarketMoversModule"]) {
    const body = section(`const ${callback} = useCallback(() => {`, "}, []);");
    assert.ok(!body.includes("setTimeout"), `${callback} must only run when the user asks for it`);
    assert.ok(!body.includes("setInterval"), `${callback} must not schedule repeated retries`);
  }
});

test("each Overview section still settles independently of its siblings", () => {
  // The three fetch effects remain separate, each with its own status, so a
  // failure in one cannot gate another.
  assert.ok(source.includes("dispatchOverview({"));
  assert.ok(source.includes("dispatchTopChase({"));
  assert.ok(source.includes("dispatchMarketMovers({"));
  // Set Value must not be gated on the movers or top-chase status.
  const setValueBlock = section('<SectionErrorBoundary sectionName="overview-set-value"', "</SectionErrorBoundary>");
  assert.ok(!setValueBlock.includes("moversTickerStatus"), "Set Value must not depend on the movers status");
  assert.ok(!setValueBlock.includes("topPricedCardsStatus"), "Set Value must not depend on the top-chase status");

  const opvcBlock = section('<SectionErrorBoundary sectionName="overview-performance-vs-cost"', "</SectionErrorBoundary>");
  assert.ok(!opvcBlock.includes("moversTickerStatus"), "Opening Profit vs Cost must not depend on the movers status");
  assert.ok(!opvcBlock.includes("topPricedCardsStatus"), "Opening Profit vs Cost must not depend on the top-chase status");
});
