import { spawn, spawnSync } from "node:child_process";
import { connect } from "node:net";
import { readFileSync } from "node:fs";

const ROOT = process.cwd();
const FIXTURE_PORT = 8011;
const NEXT_PORT = 3130;
const mode = process.argv.includes("--capture") ? "capture" : "verify";
const skipBuild = process.argv.includes("--skip-build");

function run(command, args, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: ROOT, env: { ...process.env, ...env }, stdio: "inherit", shell: true });
    child.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`)));
  });
}

async function waitFor(url, label) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`${label} did not become ready: ${url}`);
}

async function waitForPort(port, label) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const ready = await new Promise((resolve) => {
      const socket = connect({ host: "127.0.0.1", port }, () => { socket.destroy(); resolve(true); });
      socket.on("error", () => resolve(false));
    });
    if (ready) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`${label} did not listen on port ${port}`);
}

const backend = `http://127.0.0.1:${FIXTURE_PORT}`;
for (const port of [FIXTURE_PORT, NEXT_PORT]) {
  const occupied = await new Promise((resolve) => {
    const socket = connect({ host: "127.0.0.1", port }, () => { socket.destroy(); resolve(true); });
    socket.on("error", () => resolve(false));
  });
  if (occupied) throw new Error(`Audit port ${port} is already occupied`);
}
if (!skipBuild) {
  await run("npm.cmd", ["run", "build"], { BACKEND_API_BASE_URL: backend, NEXT_PUBLIC_BACKEND_API_BASE_URL: backend });
}

const fixture = spawn("node", [".perf-audit/set-rich-fixture-server.mjs"], {
  cwd: ROOT,
  env: { ...process.env, FIXTURE_MODE: "playback", FIXTURE_PORT: String(FIXTURE_PORT) },
  stdio: "inherit",
});
const next = spawn("npm.cmd", ["run", "start", "--", "--hostname", "127.0.0.1", "--port", String(NEXT_PORT)], {
  cwd: ROOT,
  env: { ...process.env, BACKEND_API_BASE_URL: backend, NEXT_PUBLIC_BACKEND_API_BASE_URL: backend },
  stdio: "inherit",
  shell: true,
});

function terminate(child) {
  if (!child?.pid) return;
  if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else child.kill("SIGTERM");
}

try {
  await waitFor(`${backend}/__fixture__/health`, "fixture server");
  const manifest = JSON.parse(readFileSync(".perf-audit/fixtures/set-rich-v1/manifest.json", "utf8"));
  for (const [route, entry] of Object.entries(manifest.routes)) {
    if (entry.critical === false) continue;
    const response = await fetch(`${backend}${route}`);
    if (!response.ok) throw new Error(`Critical fixture preflight failed: ${route} HTTP ${response.status}`);
  }
  await waitForPort(NEXT_PORT, "Next production server");
  await run("node", [".perf-audit/set-rich-visual-parity.mjs", `--${mode}`], {
    BASE: `http://127.0.0.1:${NEXT_PORT}`,
    SET_VISUAL_BASELINE: "set-rich-fixture-v2",
  });
  const report = await (await fetch(`${backend}/__fixture__/report`)).json();
  console.log(JSON.stringify(report, null, 2));
  if (report.unexpectedRequests.length || report.unusedCriticalFixtures.length) {
    throw new Error("Fixture completeness assertion failed");
  }
} finally {
  terminate(next);
  terminate(fixture);
}
