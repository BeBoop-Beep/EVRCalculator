import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
await p.goto("http://localhost:3100/Market", { waitUntil: "domcontentloaded", timeout: 300000 });
const ol = p.locator("ol[aria-label^='Sets ordered']");
await ol.locator("li").first().waitFor({ timeout: 300000 });
await p.waitForTimeout(1200);
await ol.screenshot({ path: ".shot-mobile.png" });
console.log(JSON.stringify(await ol.locator("li").first().evaluate((li) => {
  const rowEl = li.firstElementChild, cs = getComputedStyle(rowEl);
  const content = rowEl.getBoundingClientRect().width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const q = (s) => { const e = li.querySelector(s); const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
  const nav = li.querySelector("a[data-ranking-nav]");
  return { content: Math.round(content), rowCols: cs.gridTemplateColumns, navCols: getComputedStyle(nav).gridTemplateColumns,
    nav: q("a[data-ranking-nav]"), rank: q("a[data-ranking-nav] > span:first-child"), logo: q("a[data-ranking-nav] > img, a[data-ranking-nav] > span.flex.h-9"),
    value: q('[data-ranking-value="compact"]'), chart: q("[data-ranking-chart]"), svg: q("[data-market-sparkline] svg"), dates: q("[data-market-sparkline-dates]"),
    valueNavVisible: !!li.querySelector("a[data-ranking-value-nav]")?.offsetParent,
    navContainsChart: nav.contains(li.querySelector("[data-market-sparkline]")) };
}), null, 1));
await b.close();
