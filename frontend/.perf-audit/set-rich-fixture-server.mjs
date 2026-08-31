import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PORT = Number(process.env.FIXTURE_PORT || 8011);
const MODE = process.env.FIXTURE_MODE || "playback";
const LIVE_BASE = process.env.LIVE_BACKEND_BASE || "http://127.0.0.1:8001";
const ROOT = join(process.cwd(), ".perf-audit", "fixtures", "set-rich-v1");
const MANIFEST_PATH = join(ROOT, "manifest.json");
const DEBUG = process.env.SET_FIXTURE_DEBUG === "1";
const manifest = existsSync(MANIFEST_PATH)
  ? JSON.parse(readFileSync(MANIFEST_PATH, "utf8"))
  : { version: 1, capturedAt: null, routes: {} };
const observed = new Map();
const unexpected = [];

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
  return path.startsWith("/tcgs/pokemon/");
}

function json(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  response.end(`${JSON.stringify(payload)}\n`);
}

function report() {
  const critical = Object.entries(manifest.routes).filter(([, entry]) => entry.critical !== false);
  return {
    mode: MODE,
    expectedRequests: Object.keys(manifest.routes).length,
    observedRequests: [...observed.entries()].map(([route, count]) => ({ route, count })),
    unexpectedRequests: unexpected,
    unusedCriticalFixtures: critical.filter(([route]) => !observed.has(route)).map(([route]) => route),
  };
}

const server = createServer(async (request, response) => {
  const key = canonicalUrl(request.url || "/");
  if (key === "/__fixture__/health") return json(response, 200, { ok: true, mode: MODE });
  if (key === "/__fixture__/report") return json(response, 200, report());
  if (request.method !== "GET" || !allowed(key)) {
    unexpected.push(`${request.method} ${key}`);
    return json(response, 501, { error: "unexpected_fixture_request", method: request.method, route: key });
  }
  observed.set(key, (observed.get(key) || 0) + 1);
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
    unexpected.push(`GET ${key}`);
    return json(response, 404, { error: "missing_fixture", route: key });
  }
  response.writeHead(entry.status, { "content-type": entry.contentType, "cache-control": "no-store" });
  response.end(readFileSync(join(ROOT, entry.file)));
});

server.listen(PORT, "127.0.0.1", () => console.log(`Set fixture ${MODE} server listening on http://127.0.0.1:${PORT}`));

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
