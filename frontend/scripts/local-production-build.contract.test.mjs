import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const wrapper = await readFile(new URL("./local-production-build.mjs", import.meta.url), "utf8");
const config = await readFile(new URL("../next.config.mjs", import.meta.url), "utf8");

test("local production builds use an isolated Next distDir on Windows-compatible Node", () => {
  assert.equal(packageJson.scripts.build, "node scripts/local-production-build.mjs");
  assert.match(wrapper, /process\.env\.VERCEL === "1"/);
  assert.match(wrapper, /PERF_AUDIT_DIST_DIR = "\.next-build"/);
  assert.match(wrapper, /spawn\(process\.execPath/);
  assert.match(config, /process\.env\.PERF_AUDIT_DIST_DIR/);
});
