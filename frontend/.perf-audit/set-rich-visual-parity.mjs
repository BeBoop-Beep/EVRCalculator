import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3100";
const ROOT = join(process.cwd(), ".perf-audit", "baselines", "set-rich");
const SNAPSHOT_FILE = join(ROOT, "geometry.json");
const MODE = process.argv.includes("--capture") ? "capture" : process.argv.includes("--verify") ? "verify" : null;
const TOLERANCE = Number(process.env.GEOMETRY_TOLERANCE || 3);
const DEBUG = process.env.SET_PARITY_DEBUG === "1";

if (!MODE) throw new Error("Use --capture or --verify. Verification never overwrites the baseline.");
if (MODE === "verify" && !existsSync(SNAPSHOT_FILE)) throw new Error(`Missing baseline: ${SNAPSHOT_FILE}`);

const viewports = [
  ["desktop", { width: 1440, height: 900 }],
  ["below-boundary", { width: 1199, height: 900 }],
  ["boundary", { width: 1200, height: 900 }],
  ["above-boundary", { width: 1201, height: 900 }],
  ["mobile", { width: 412, height: 915 }],
];
const tabs = [
  ["rip", ""],
  ["market", "?tab=market"],
  ["cards", "?tab=cards"],
  ["pull-rates", "?tab=pull-rates"],
];
const allCases = [
  ...viewports.flatMap(([viewportName, viewport]) =>
    tabs.map(([tab, query]) => ({ set: "prismatic-evolutions", viewportName, viewport, tab, query }))),
  ...tabs.map(([tab, query]) => ({
    set: "ascended-heroes",
    viewportName: "desktop",
    viewport: { width: 1440, height: 900 },
    tab,
    query,
  })),
];
const caseFilter = process.env.CASE_FILTER ? new RegExp(process.env.CASE_FILTER) : null;
const cases = caseFilter
  ? allCases.filter((entry) => caseFilter.test(`${entry.set}__${entry.viewportName}__${entry.tab}`))
  : allCases;

const commonSelectors = {
  contextShell: "[data-set-context-shell]",
  contextHeader: "[data-set-context-header]",
  stickyTabs: "[data-set-detail-sticky-tabs]",
};
const tabSelectors = {
  rip: { root: "#set-detail-overview" },
  market: {
    root: "#set-detail-market",
    movers: "#set-detail-market-movers",
    setValue: "#set-detail-market-set-value",
    topChase: "#set-detail-market-top-chase",
  },
  cards: {
    root: "#set-detail-cards",
    grid: "#set-detail-cards .grid.grid-cols-2",
  },
  "pull-rates": { root: "#set-detail-pull-rates" },
};
const labels = ["RIP", "Market", "Cards & Products", "Pull Rates"];

function shotPath(key) {
  return join(ROOT, `${key}.png`);
}

function closeEnough(expected, actual) {
  if (expected === actual) return true;
  if (typeof expected !== "number" || typeof actual !== "number") return false;
  return Math.abs(expected - actual) <= TOLERANCE;
}

function compareGeometry(expected, actual, path = "") {
  const failures = [];
  for (const key of new Set([...Object.keys(expected || {}), ...Object.keys(actual || {})])) {
    const nextPath = path ? `${path}.${key}` : key;
    const left = expected?.[key];
    const right = actual?.[key];
    if (left === undefined) continue;
    if (left && right && typeof left === "object" && typeof right === "object") {
      failures.push(...compareGeometry(left, right, nextPath));
    } else if (!closeEnough(left, right)) {
      failures.push(`${nextPath}: expected ${JSON.stringify(left)}, received ${JSON.stringify(right)}`);
    }
  }
  return failures;
}

async function fingerprint(page, selectors) {
  return page.evaluate(({ selectors, labels }) => {
    const geometry = {};
    for (const [name, selector] of Object.entries(selectors)) {
      const element = document.querySelector(selector);
      const style = element ? getComputedStyle(element) : null;
      const rect = element?.getBoundingClientRect();
      geometry[name] = {
        exists: Boolean(element),
        visible: Boolean(element && rect && rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden"),
        x: rect ? Math.round(rect.x * 10) / 10 : null,
        y: rect ? Math.round(rect.y * 10) / 10 : null,
        width: rect ? Math.round(rect.width * 10) / 10 : null,
        height: rect ? Math.round(rect.height * 10) / 10 : null,
        display: style?.display || null,
        position: style?.position || null,
        gridTemplateColumns: style?.gridTemplateColumns || null,
        childCount: element?.children?.length ?? null,
      };
    }
    const visibleLabels = Object.fromEntries(labels.map((label) => [
      label,
      [...document.querySelectorAll("button,a,h1,h2,h3,p,span")].some((node) =>
        node.textContent?.trim() === label && node.getBoundingClientRect().width > 0),
    ]));
    visibleLabels["Market Value Trend"] = document.body.innerText.includes("Market Value Trend");
    visibleLabels["Set Signals"] = document.body.innerText.includes("Set Signals");
    return { geometry, visibleLabels };
  }, { selectors, labels });
}

async function stabilize(page) {
  await page.addStyleTag({ content: `
    *, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
    html { scroll-behavior: auto !important; }
  ` });
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(5000);
}

const expected = MODE === "verify" ? JSON.parse(readFileSync(SNAPSHOT_FILE, "utf8")) : {};
const actual = MODE === "capture" && existsSync(SNAPSHOT_FILE)
  ? JSON.parse(readFileSync(SNAPSHOT_FILE, "utf8"))
  : {};
const failures = [];
mkdirSync(ROOT, { recursive: true });
const browser = await chromium.launch();

try {
  for (const testCase of cases) {
    const key = `${testCase.set}__${testCase.viewportName}__${testCase.tab}`;
    const context = await browser.newContext({ viewport: testCase.viewport });
    const page = await context.newPage();
    const pageErrors = [];
    const startedAt = Date.now();
    const url = `${BASE}/TCGs/Pokemon/Sets/${testCase.set}${testCase.query}`;
    page.on("pageerror", (error) => {
      const detail = error.stack || error.message;
      pageErrors.push(detail);
      if (DEBUG) console.error(`[set-parity:pageerror +${Date.now() - startedAt}ms] ${key} ${page.url()}\n${detail}`);
    });
    if (DEBUG) {
      page.on("console", (message) => {
        if (message.type() === "error" || message.type() === "warning") {
          console.error(`[set-parity:console:${message.type()} +${Date.now() - startedAt}ms] ${key} ${message.text()}`);
        }
      });
      page.on("requestfailed", (request) => {
        console.error(`[set-parity:requestfailed +${Date.now() - startedAt}ms] ${key} ${request.method()} ${request.url()} ${request.failure()?.errorText || "unknown"}`);
      });
      console.error(`[set-parity:start] ${key} ${testCase.viewport.width}x${testCase.viewport.height} ${url}`);
    }
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForSelector("[data-set-context-shell]", { timeout: 90000 });
    const selectors = { ...commonSelectors, ...tabSelectors[testCase.tab] };
    await page.waitForSelector(selectors.root, { timeout: 90000 });
    await stabilize(page);
    actual[key] = await fingerprint(page, selectors);

    const masks = [
      page.locator("svg.recharts-surface"),
      page.locator("img"),
      page.locator("#set-detail-cards .grid.grid-cols-2"),
    ];
    const screenshot = await page.screenshot({ fullPage: true, animations: "disabled", mask: masks });
    const hash = createHash("sha256").update(screenshot).digest("hex");
    actual[key].screenshotSha256 = hash;
    if (MODE === "capture") {
      writeFileSync(shotPath(key), screenshot);
    } else {
      failures.push(...compareGeometry(expected[key]?.geometry || {}, actual[key].geometry, `${key}.geometry`));
      failures.push(...compareGeometry(expected[key]?.visibleLabels || {}, actual[key].visibleLabels, `${key}.labels`));
      if (expected[key]?.screenshotSha256 !== hash) {
        const received = join(ROOT, "received", `${key}.png`);
        mkdirSync(dirname(received), { recursive: true });
        writeFileSync(received, screenshot);
        failures.push(`${key}.screenshot: expected ${expected[key]?.screenshotSha256}, received ${hash}; wrote ${received}`);
      }
    }
    if (pageErrors.length) failures.push(`${key}.pageErrors: ${pageErrors.join(" | ")}`);
    console.log(`${MODE} ${key}`);
    await context.close();
  }
} finally {
  await browser.close();
}

if (MODE === "capture") {
  writeFileSync(SNAPSHOT_FILE, `${JSON.stringify(actual, null, 2)}\n`);
  console.log(`Captured ${cases.length} approved rich Set cases in ${ROOT}`);
} else if (failures.length) {
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Verified ${cases.length} rich Set cases within ${TOLERANCE}px geometry tolerance.`);
}
