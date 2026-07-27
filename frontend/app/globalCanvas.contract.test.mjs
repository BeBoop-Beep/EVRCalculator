import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const appDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.dirname(appDir);
const read = (relativePath) =>
  fs.readFileSync(path.join(frontendDir, relativePath), "utf8").replace(/\r\n/g, "\n");

test("the application canvas has one near-black navy token distinct from elevated surfaces", () => {
  const globals = read("app/styles/globals.css");
  const layout = read("app/layout.js");

  assert.ok(globals.includes("--app-background: #050b14;"));
  assert.ok(globals.includes("--app-background-elevated: #07111f;"));
  assert.ok(globals.includes("--app-background-subtle: #091525;"));
  assert.ok(globals.includes("--surface-page: #09101b;"));
  assert.match(globals, /body \{[\s\S]+background-color: var\(--app-background\);/);
  assert.match(globals, /html \{[\s\S]+background-color: var\(--app-background\);/);
  assert.match(globals, /\.app-canvas \{[\s\S]+background-color: var\(--app-background\);/);
  assert.ok(layout.includes('<main className="app-canvas '));
  assert.match(
    globals,
    /\.index-loader-shell--fullscreen \{[\s\S]+background-color: var\(--app-background\);/
  );
});

test("legacy full-page wrappers use the shared canvas without changing component surfaces", () => {
  const canvasFiles = [
    "app/global-error.js",
    "app/TCGs/Pokemon/page.js",
    "app/TCGs/Pokemon/Analytics/page.js",
    "app/TCGs/Pokemon/Sets/page.js",
    "app/TCGs/Pokemon/Sets/loading.js",
    "app/waitlist/verify/page.js",
    "app/waitlist/verified/page.js",
    "components/Products/ProductDetails.js",
    "components/Featured.js",
  ];

  for (const relativePath of canvasFiles) {
    const source = read(relativePath);
    assert.ok(
      source.includes("var(--app-background)"),
      `${relativePath} must use the shared application canvas`
    );
    assert.ok(!source.includes("bg-[#020817]"), `${relativePath} must not retain the legacy canvas`);
  }

  const globals = read("app/styles/globals.css");
  assert.ok(globals.includes("--set-glass-bg: rgba(8, 17, 31, 0.40);"));
  assert.ok(globals.includes("--set-glass-bg-dense: rgba(8, 17, 31, 0.52);"));
});
