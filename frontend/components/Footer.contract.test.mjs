import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "Footer.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

test("the footer Product column no longer offers Tools", () => {
  assert.ok(!source.includes('href: "/tools"'), "no footer link may point at /tools");
  assert.ok(!/label: "Tools"/.test(source), "the Tools label must be removed");
});

test("the footer exposes the public architecture and preserves existing destinations", () => {
  for (const href of ["/Rankings", "/Market", "/Research", "/TCGs", "/my-collection", "/about", "/blog", "/careers", "/contact", "/terms", "/privacy", "/cookies"]) {
    assert.ok(source.includes(`href: "${href}"`), `${href} must survive`);
  }
});

test("the footer column structure is untouched", () => {
  const headings = [...source.matchAll(/heading: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(headings, ["Product", "Company", "Legal", "Support"], "the columns and their headings are unchanged");
});
