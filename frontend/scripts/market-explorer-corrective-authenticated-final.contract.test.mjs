import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./market-explorer-corrective-authenticated-final.mjs", import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("authenticated corrective runner fails closed before Explorer navigation", () => {
  const gate = source.indexOf('context.request.get(`${origin}/api/auth/me`)');
  const navigation = source.indexOf('page.goto(`${origin}/Market/Explorer`');
  assert.ok(gate > 0 && navigation > gate);
  assert.match(source, /AUTHENTICATED_ACCEPTANCE_SESSION_REQUIRED/);
  assert.match(source, /\["plus", "premium"\]\.includes\(plan\)/);
});

test("token stays local and cannot enter evidence", () => {
  assert.match(source, /EXPLORER_AUTH_TOKEN_FILE/);
  assert.match(source, /tokenIsInsideRepository/);
  assert.match(source, /token = undefined/);
  assert.doesNotMatch(source, /JSON\.stringify\([^\n]*token/);
  assert.doesNotMatch(source, /console\.(?:log|error)\([^\n]*token/);
  assert.doesNotMatch(source, /authorization/i);
  assert.match(source, /tokenLogged: false, tokenPersisted: false, tokenPathPersisted: false/);
});

test("runner covers only every outstanding scenario and all required viewports", () => {
  for (const number of [2, 4, 5, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19, 20]) {
    assert.match(source, new RegExp(`mark\\(${number},`), `missing scenario ${number}`);
  }
  for (const viewport of ["1728x1000", "1440x900", "1024x768", "768x1024", "390x844", "844x390"]) assert.match(source, new RegExp(viewport));
  for (const output of ["network.json", "measurements.json", "authenticated-final-evidence.json"]) assert.match(source, new RegExp(output.replace(".", "\\.")));
});

test("network receipts and forbidden live failures are explicit", () => {
  for (const field of ["method", "path", "status", "elapsedMs"]) assert.match(source, new RegExp(`${field}:`));
  for (const code of ["GENERATION_MISMATCH", "CATALOG_SEARCH_UNAVAILABLE", "ACTIVITY_GENERATION_MISMATCH", "PREPARED_COMPARISON_TIMEOUT"]) assert.match(source, new RegExp(code));
  assert.match(source, /response\.status\(\) >= 500/);
  assert.match(source, /consoleErrors\.length === 0/);
});
