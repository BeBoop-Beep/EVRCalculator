import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

// middleware.js imports via the `@/` alias (jsconfig.json), which this
// project's plain `tsx --test` runner cannot resolve (no tsconfig.json) —
// the same reason every other alias-importing route/component in this repo
// is covered by a source contract test rather than a live import. The actual
// URL/security logic this file delegates to (sanitizeReturnPath) has full
// behavioral coverage in lib/auth/returnPath.test.mjs.
const source = fs.readFileSync(new URL("./middleware.js", import.meta.url), "utf8");

test("protected-route redirects preserve the requested pathname+search as a sanitized next", () => {
  assert.match(source, /import \{ sanitizeReturnPath \} from "@\/lib\/auth\/returnPath\.mjs"/);
  assert.match(source, /const requestedPath = `\$\{req\.nextUrl\.pathname\}\$\{req\.nextUrl\.search\}`/);
  assert.match(source, /loginUrl\.searchParams\.set\("next", sanitizeReturnPath\(requestedPath\)\)/);
});

test("next is derived through the shared sanitizer, so it can never become an open redirect", () => {
  assert.doesNotMatch(source, /searchParams\.set\("next",\s*requestedPath\)/);
});

test("the protected-route list guarding this behavior is unchanged", () => {
  assert.match(source, /"\/dashboard"/);
  assert.match(source, /"\/profile"/);
  assert.match(source, /"\/my-portfolio"/);
  assert.match(source, /"\/my-collection"/);
  assert.match(source, /"\/account-settings"/);
});

test("Profile/Portfolio surfaces (/profile, /my-portfolio, /my-collection, /u) are temporarily blocked", () => {
  const blockedBlock = source.slice(
    source.indexOf("const TEMPORARILY_BLOCKED_ROUTES"),
    source.indexOf("];", source.indexOf("const TEMPORARILY_BLOCKED_ROUTES"))
  );
  for (const route of ['"/profile"', '"/my-portfolio"', '"/my-collection"', '"/u"']) {
    assert.ok(blockedBlock.includes(route), `${route} must be in TEMPORARILY_BLOCKED_ROUTES`);
  }
  // /account-settings must NOT be in the temporary-block list — it stays reachable.
  assert.ok(!blockedBlock.includes('"/account-settings"'), "/account-settings must not be temporarily blocked");
});

test("blocked routes redirect home, not through a Profile/Portfolio nav slot pointed at /pricing", () => {
  const blockFnBody = source.slice(
    source.indexOf("function blockTemporarilyUnavailableRoutes"),
    source.indexOf("export function middleware")
  );
  assert.match(blockFnBody, /homeUrl\.pathname = "\/";/);
  assert.doesNotMatch(blockFnBody, /\/pricing/);
});

test("matchesRoute blocks exact and nested paths for every temporarily blocked route", () => {
  // Source-level sanity: matchesRoute is reused for both the block list and the
  // protected-route auth gate, so nested paths like /profile/anything and
  // /u/example/collection are covered by the same startsWith(`${route}/`) rule.
  assert.match(source, /pathname === route \|\| pathname\.startsWith\(`\$\{route\}\/`\)/);
});
