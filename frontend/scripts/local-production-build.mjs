import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const nextCli = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const hostedBuild = process.env.VERCEL === "1";
const env = { ...process.env };

if (!hostedBuild && !env.PERF_AUDIT_DIST_DIR) {
  env.PERF_AUDIT_DIST_DIR = `.next-build-${process.pid}`;
}

if (env.PERF_AUDIT_DIST_DIR) {
  console.log(`[build] isolated distDir: ${env.PERF_AUDIT_DIST_DIR}`);
}

const child = spawn(process.execPath, [nextCli, "build", ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env,
  stdio: "inherit",
  windowsHide: true,
});

child.on("error", (error) => {
  console.error("[build] failed to start Next.js", { error: error.message });
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  if (signal) console.error("[build] Next.js terminated", { signal });
  process.exitCode = code ?? 1;
});
