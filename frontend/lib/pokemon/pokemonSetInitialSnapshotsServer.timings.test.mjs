import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const snapshotsServerPath = path.resolve(__dirname, "pokemonSetInitialSnapshotsServer.js");
const setRoutePath = path.resolve(__dirname, "../../app/TCGs/Pokemon/Sets/[setSlug]/page.js");

// ---------------------------------------------------------------------------
// pokemonSetInitialSnapshotsServer – timings shape
// ---------------------------------------------------------------------------

test("getPokemonSetInitialSnapshots timings includes totalMs alongside cardsMs and marketDashboardMs", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetInitialSnapshots");
  const fnSource = source.slice(fnStart);

  assert.ok(fnSource.includes("const startedAt = Date.now()"), "must have startedAt before Promise.all");
  assert.ok(fnSource.includes("const totalMs = Date.now() - startedAt"), "must compute totalMs from startedAt");
  assert.ok(fnSource.includes("totalMs,"), "must include totalMs in return timings object (shorthand)");
  assert.ok(fnSource.includes("cardsMs: cards.elapsedMs"), "must preserve cardsMs");
  assert.ok(fnSource.includes("marketDashboardMs: marketDashboard.elapsedMs"), "must preserve marketDashboardMs");
});

test("getPokemonSetInitialSnapshots emits structured info log with timing and error fields", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const logStart = source.indexOf('console.info("[set-snapshots-server] snapshots_loaded"');

  assert.ok(logStart >= 0, "must emit [set-snapshots-server] snapshots_loaded log");

  const logEnd = source.indexOf(");", logStart);
  const logSource = source.slice(logStart, logEnd);

  assert.ok(logSource.includes("setId"), "log includes setId");
  assert.ok(logSource.includes("cardsMs"), "log includes cardsMs");
  assert.ok(logSource.includes("marketDashboardMs"), "log includes marketDashboardMs");
  assert.ok(logSource.includes("totalMs"), "log includes totalMs");
  assert.ok(logSource.includes("cardsError"), "log includes cardsError");
  assert.ok(logSource.includes("marketDashboardError"), "log includes marketDashboardError");
});

test("getPokemonSetInitialSnapshots totalMs is placed before the return statement", () => {
  const source = fs.readFileSync(snapshotsServerPath, "utf8");
  const fnStart = source.indexOf("export async function getPokemonSetInitialSnapshots");
  const totalMsIndex = source.indexOf("const totalMs = Date.now() - startedAt", fnStart);
  const returnIndex = source.indexOf("return {", totalMsIndex);

  assert.ok(totalMsIndex > fnStart, "totalMs must be inside getPokemonSetInitialSnapshots");
  assert.ok(returnIndex > totalMsIndex, "totalMs must be computed before the return");
});

// ---------------------------------------------------------------------------
// page.js route – timing instrumentation
// ---------------------------------------------------------------------------

test("set page route captures targetsMs with bookend timestamps around getRipStatisticsTargets", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const targetsStartIndex = source.indexOf("const targetsStartedAt = Date.now()");
  const targetsCallIndex = source.indexOf("getRipStatisticsTargets(", targetsStartIndex);
  const targetsMsIndex = source.indexOf("const targetsMs = Date.now() - targetsStartedAt", targetsCallIndex);

  assert.ok(targetsStartIndex >= 0, "must have targetsStartedAt");
  assert.ok(targetsCallIndex > targetsStartIndex, "getRipStatisticsTargets must be called after targetsStartedAt");
  assert.ok(targetsMsIndex > targetsCallIndex, "targetsMs must be computed after getRipStatisticsTargets");
});

test("set page route captures explorePagePayloadMs inside the async IIFE", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const iifeStart = source.indexOf("const startedAt = Date.now();");
  const exploreCall = source.indexOf("getExplorePagePayload(", iifeStart);
  const elapsedSuccess = source.indexOf("elapsedMs: Date.now() - startedAt", exploreCall);
  const elapsedCatch = source.indexOf("elapsedMs: Date.now() - startedAt", elapsedSuccess + 1);
  const captureIndex = source.indexOf("explorePagePayloadMs = exploreResult.elapsedMs");

  assert.ok(iifeStart >= 0, "must have startedAt inside explore IIFE");
  assert.ok(exploreCall > iifeStart, "explore call must follow startedAt");
  assert.ok(elapsedSuccess > exploreCall, "elapsedMs must be returned on success path");
  assert.ok(elapsedCatch > elapsedSuccess, "elapsedMs must also be returned on error path");
  assert.ok(captureIndex >= 0, "explorePagePayloadMs must be captured from exploreResult.elapsedMs");
});

test("set page route computes routeTotalMs from routeStartedAt after all async work", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const routeStartIndex = source.indexOf("const routeStartedAt = Date.now()");
  const promiseAllIndex = source.indexOf("await Promise.all(", routeStartIndex);
  const routeTotalMsIndex = source.indexOf("const routeTotalMs = Date.now() - routeStartedAt", promiseAllIndex);

  assert.ok(routeStartIndex >= 0, "must have routeStartedAt at the top of the route");
  assert.ok(promiseAllIndex > routeStartIndex, "Promise.all must come after routeStartedAt");
  assert.ok(routeTotalMsIndex > promiseAllIndex, "routeTotalMs must be computed after Promise.all resolves");
});

test("set page route emits structured info log with all required timing and context fields", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const logStart = source.indexOf('console.info("[set-page-route] timings"');

  assert.ok(logStart >= 0, "must emit [set-page-route] timings log");

  const logEnd = source.indexOf(");", logStart);
  const logSource = source.slice(logStart, logEnd);

  assert.ok(logSource.includes("setSlug"), "log includes setSlug");
  assert.ok(logSource.includes("requestedTargetId"), "log includes requestedTargetId");
  assert.ok(logSource.includes("targetsMs"), "log includes targetsMs");
  assert.ok(logSource.includes("explorePagePayloadMs"), "log includes explorePagePayloadMs");
  assert.ok(logSource.includes("initialCardsSnapshotMs"), "log includes initialCardsSnapshotMs");
  assert.ok(logSource.includes("initialMarketDashboardSnapshotMs"), "log includes initialMarketDashboardSnapshotMs");
  assert.ok(logSource.includes("initialModuleSnapshotsTotalMs"), "log includes initialModuleSnapshotsTotalMs");
  assert.ok(logSource.includes("routeTotalMs"), "log includes routeTotalMs");
  assert.ok(logSource.includes("targetsFallback"), "log includes targetsFallback");
  assert.ok(logSource.includes("explorePayloadFallback"), "log includes explorePayloadFallback");
  assert.ok(logSource.includes("snapshotErrors"), "log includes snapshotErrors");
});

test("set page route log maps snapshotTimings fields to named log keys without mutation", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const snapshotTimingsIndex = source.indexOf("const snapshotTimings = initialModuleSnapshots?.timings || {}");

  assert.ok(snapshotTimingsIndex >= 0, "must read snapshotTimings from initialModuleSnapshots.timings");

  const logStart = source.indexOf('console.info("[set-page-route] timings"', snapshotTimingsIndex);
  const logEnd = source.indexOf(");", logStart);
  const logSource = source.slice(logStart, logEnd);

  assert.ok(logSource.includes("snapshotTimings.cardsMs"), "log reads cardsMs from snapshotTimings");
  assert.ok(logSource.includes("snapshotTimings.marketDashboardMs"), "log reads marketDashboardMs from snapshotTimings");
  assert.ok(logSource.includes("snapshotTimings.totalMs"), "log reads totalMs from snapshotTimings");
});

test("set page route merges route timings non-destructively into initialModuleSnapshots.timings", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  // Find the reassignment (not the initial `let` declaration) by anchoring on the timing merge comment region
  const routeTotalMsIndex = source.indexOf("const routeTotalMs = Date.now() - routeStartedAt");
  const mergeStart = source.indexOf("initialModuleSnapshots = {", routeTotalMsIndex);
  const mergeEnd = source.indexOf("};", mergeStart);
  const mergeSource = source.slice(mergeStart, mergeEnd);

  assert.ok(mergeSource.includes("...initialModuleSnapshots"), "must spread existing initialModuleSnapshots fields");
  assert.ok(mergeSource.includes("timings: {"), "must include timings key in merge");
  assert.ok(mergeSource.includes("...snapshotTimings"), "must spread existing snapshotTimings to preserve cardsMs etc.");
  assert.ok(mergeSource.includes("targetsMs,"), "must include targetsMs in merged timings");
  assert.ok(mergeSource.includes("explorePagePayloadMs,"), "must include explorePagePayloadMs in merged timings");
  assert.ok(mergeSource.includes("routeTotalMs,"), "must include routeTotalMs in merged timings");
});

test("set page route still passes all original props to PokemonSetPageClient after timing merge", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const clientStart = source.indexOf("<PokemonSetPageClient");
  const clientEnd = source.indexOf("/>", clientStart);
  const clientSource = source.slice(clientStart, clientEnd);

  assert.ok(clientSource.includes("targetsPayload={targetsPayload}"), "passes targetsPayload");
  assert.ok(clientSource.includes("selectedTarget={effectiveSelectedTarget}"), "passes selectedTarget");
  assert.ok(clientSource.includes("requestedTargetType={requestedTargetType}"), "passes requestedTargetType");
  assert.ok(clientSource.includes("requestedTargetId={requestedTargetId}"), "passes requestedTargetId");
  assert.ok(clientSource.includes("explorePayload={explorePayload}"), "passes explorePayload");
  assert.ok(clientSource.includes("initialModuleSnapshots={initialModuleSnapshots}"), "passes initialModuleSnapshots");
  assert.ok(clientSource.includes("pageError={pageError}"), "passes pageError");
  assert.ok(clientSource.includes('profileBaseHref="/TCGs/Pokemon/Sets"'), "passes profileBaseHref");
  assert.ok(clientSource.includes("targetHrefById={targetHrefById}"), "passes targetHrefById");
});

test("set page route snapshot fallback catch block is unchanged by timing instrumentation", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  // Anchor on the snapshots catch, not the targets catch which appears first
  const snapshotsCatchAnchor = source.indexOf("getPokemonSetInitialSnapshots(requestedTargetId, { tab: activeSetDetailTab }).catch");
  const catchStart = source.indexOf(".catch((error) => ({", snapshotsCatchAnchor);
  const catchEnd = source.indexOf("}))", catchStart);
  const catchSource = source.slice(catchStart, catchEnd);

  assert.ok(catchSource.includes("...initialModuleSnapshots"), "catch spreads initialModuleSnapshots");
  assert.ok(catchSource.includes("moduleSnapshots:"), "catch sets moduleSnapshots error key");
  assert.ok(catchSource.includes("message: error?.message"), "catch preserves error message");
  assert.ok(!catchSource.includes("routeTotalMs"), "catch block does not contain routeTotalMs (added in merge step)");
  assert.ok(!catchSource.includes("targetsMs"), "catch block does not contain targetsMs (added in merge step)");
});

// ---------------------------------------------------------------------------
// Active tab payload must not be raced against a fixed timeout budget —
// the active tab's shell + cards/market-dashboard snapshot is critical
// content and must be awaited in full (see pokemonSetInitialSnapshotsServer's
// own per-request timeout/fallback for the actual degrade-gracefully path).
// ---------------------------------------------------------------------------

test("set page route does not race the active tab module snapshot against a fixed timeout budget", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");

  assert.ok(!source.includes("MODULE_SNAPSHOT_BUDGET_MS"), "must not define a fixed module snapshot timeout budget");
  assert.ok(!source.includes("Promise.race(["), "must not race the snapshot promise against a timeout");
});

test("set page route awaits the active tab module snapshot promise directly", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");
  const promiseAllStart = source.indexOf("const [exploreResult, moduleSnapshotsResult] = await Promise.all([");
  const promiseAllEnd = source.indexOf("]);", promiseAllStart);
  const promiseAllSource = source.slice(promiseAllStart, promiseAllEnd);

  assert.ok(promiseAllStart >= 0, "must build exploreResult/moduleSnapshotsResult from Promise.all");
  assert.ok(promiseAllSource.trim().endsWith("snapshotPromise,"), "snapshotPromise must be awaited directly, not raced");
});

test("set page route snapshot promise is built with the same catch shape as before", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");

  // The catch shape must still exist on the snapshotPromise
  const catchAnchor = source.indexOf("getPokemonSetInitialSnapshots(requestedTargetId, { tab: activeSetDetailTab }).catch");
  assert.ok(catchAnchor >= 0, "must still have getPokemonSetInitialSnapshots(requestedTargetId, { tab: activeSetDetailTab }).catch");

  const catchStart = source.indexOf(".catch((error) => ({", catchAnchor);
  const catchEnd = source.indexOf("}))", catchStart);
  const catchSource = source.slice(catchStart, catchEnd);

  assert.ok(catchSource.includes("...initialModuleSnapshots"), "catch still spreads initialModuleSnapshots");
  assert.ok(catchSource.includes("moduleSnapshots:"), "catch still sets moduleSnapshots error key");
});

test("module snapshot result still falls back to the empty placeholder shape defensively", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");

  // Even though the snapshot promise is now awaited directly (not raced), a
  // falsy result must still be handled defensively without throwing.
  assert.ok(
    source.includes("initialModuleSnapshots = moduleSnapshotsResult || initialModuleSnapshots"),
    "falsy snapshot result falls back to the initial empty placeholder via ||"
  );
  // The timing merge step must still spread the placeholder timings
  const mergeIndex = source.indexOf("initialModuleSnapshots = {", source.indexOf("const routeTotalMs"));
  const mergeEnd = source.indexOf("};", mergeIndex);
  const mergeSource = source.slice(mergeIndex, mergeEnd);
  assert.ok(mergeSource.includes("...initialModuleSnapshots"), "merge still spreads placeholder fields");
  assert.ok(mergeSource.includes("...snapshotTimings"), "merge still spreads snapshot timings (empty for null result)");
});

test("set page route tracks whether snapshots were timed out and emits it in the log", () => {
  const source = fs.readFileSync(setRoutePath, "utf8");

  assert.ok(source.includes("const snapshotTimedOut ="), "must define snapshotTimedOut");
  const logStart = source.indexOf('console.info("[set-page-route] timings"');
  const logEnd = source.indexOf(");", logStart);
  const logSource = source.slice(logStart, logEnd);
  assert.ok(logSource.includes("snapshotTimedOut"), "log must include snapshotTimedOut field");
});
