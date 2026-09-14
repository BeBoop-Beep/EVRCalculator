import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createFixtureConsumption } from "./fixture-consumption.mjs";

const PORT = Number(process.env.FIXTURE_PORT || 8011);
const MODE = process.env.FIXTURE_MODE || "playback";
const LIVE_BASE = process.env.LIVE_BACKEND_BASE || "http://127.0.0.1:8001";
const SUITE = process.env.FIXTURE_SUITE || "set-rich-v1";
const ROOT = join(process.cwd(), ".perf-audit", "fixtures", SUITE);
const MANIFEST_PATH = join(ROOT, "manifest.json");
const DEBUG = process.env.SET_FIXTURE_DEBUG === "1";
const manifest = existsSync(MANIFEST_PATH)
  ? JSON.parse(readFileSync(MANIFEST_PATH, "utf8"))
  : { version: 1, capturedAt: null, routes: {} };
const consumption = createFixtureConsumption(manifest);

function canonicalUrl(requestUrl) {
  const url = new URL(requestUrl, `http://127.0.0.1:${PORT}`);
  url.searchParams.sort();
  return `${url.pathname}${url.search}`;
}

function fixtureName(key) {
  return `${createHash("sha256").update(key).digest("hex").slice(0, 16)}.json`;
}

function allowed(key) {
  const path = new URL(key, "http://fixture").pathname;
  // Recording is deliberately limited to the public Pokemon read namespace;
  // playback is stricter still and serves only exact manifest entries.
  return path.startsWith("/tcgs/pokemon/") || path.startsWith("/explore/");
}

function json(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  response.end(`${JSON.stringify(payload)}\n`);
}

function report() {
  return {
    mode: MODE,
    expectedRequests: Object.keys(manifest.routes).length,
    ...consumption.report(),
  };
}

const server = createServer(async (request, response) => {
  const key = canonicalUrl(request.url || "/");
  const phase = request.headers["x-fixture-preflight"] === "1" ? "preflight" : "browser";
  if (key === "/__fixture__/health") return json(response, 200, { ok: true, mode: MODE });
  if (key === "/__fixture__/report") return json(response, 200, report());
  if (key === "/__fixture__/reset-browser" && request.method === "POST") {
    consumption.resetBrowser();
    return json(response, 200, { ok: true });
  }
  // Anonymous visual acceptance is intentional. Keep auth deterministic without
  // requiring a recorded user fixture or treating the expected probe as noise.
  if (request.method === "GET" && key === "/auth/me") {
    consumption.record(key, { phase, expected: true, method: request.method });
    if (String(request.headers.cookie || "").includes("fixture-premium")) {
      return json(response, 200, { user: { id: "fixture-user", email: "fixture@example.test", index_plan: "premium" } });
    }
    return json(response, 401, { user: null });
  }
  if (request.method !== "GET" || !allowed(key)) {
    consumption.record(key, { phase, expected: false, method: request.method });
    return json(response, 501, { error: "unexpected_fixture_request", method: request.method, route: key });
  }
  consumption.record(key, { phase, expected: Boolean(manifest.routes[key]), method: request.method });
  if (DEBUG) console.log(`[set-fixture:${MODE}] ${request.method} ${key}`);

  if (MODE === "record") {
    const live = await fetch(`${LIVE_BASE}${key}`, { headers: { accept: "application/json" } });
    const body = await live.text();
    const name = fixtureName(key);
    mkdirSync(ROOT, { recursive: true });
    writeFileSync(join(ROOT, name), body);
    manifest.capturedAt = new Date().toISOString();
    manifest.routes[key] = { file: name, status: live.status, contentType: live.headers.get("content-type") || "application/json", critical: true };
    writeFileSync(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`);
    response.writeHead(live.status, { "content-type": manifest.routes[key].contentType, "cache-control": "no-store" });
    return response.end(body);
  }

  const entry = manifest.routes[key];
  if (!entry) {
    return json(response, 404, { error: "missing_fixture", route: key });
  }
  response.writeHead(entry.status, { "content-type": entry.contentType, "cache-control": "no-store" });
  response.end(readFileSync(join(ROOT, entry.file)));
});

server.listen(PORT, "127.0.0.1", () => console.log(`Set fixture ${MODE} server listening on http://127.0.0.1:${PORT}`));

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
