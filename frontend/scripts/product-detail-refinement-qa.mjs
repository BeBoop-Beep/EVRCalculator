import { chromium } from "playwright";

const base = "http://127.0.0.1:3010";
const products = {
  modeled: "/sealed-products/41b15cf2-512b-4b28-9660-83170538fc7a",
  guaranteed: "/sealed-products/41b15cf2-512b-4b28-9660-83170538fc7a",
  unmodeled: "/sealed-products/b6058cad-9a54-430a-90f7-7adbd0e19e1a",
};
const card = "/TCGs/Pokemon/Sets/prismaticEvolutions/Cards/71b0e9cc-968b-43f4-9f5d-4851211fbc3e";
const browser = await chromium.launch({ headless: true });
const report = { products: [], card: [] };
for (const width of [390, 768, 1024, 1280, 1440]) {
  const page = await browser.newPage({ viewport: { width, height: 1100 } });
  for (const [kind, path] of Object.entries(products)) {
    await page.goto(base + path, { waitUntil: "networkidle" });
    report.products.push(await page.evaluate(({ kind, width }) => ({
      kind, width,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      hero: Boolean(document.querySelector("[data-product-detail-hero]")),
      lock: Boolean(document.querySelector("[data-product-rip-lock]")),
      unavailable: Boolean(document.querySelector("[data-product-rip-unavailable]")),
    }), { kind, width }));
  }
  await page.goto(base + card, { waitUntil: "networkidle" });
  await page.locator("[data-card-detail-hero] img").waitFor({ state: "visible" });
  await page.waitForTimeout(200);
  report.card.push(await page.evaluate((width) => {
    const metadata = document.querySelector("[data-card-identity]").getBoundingClientRect();
    const image = document.querySelector("[data-card-detail-hero] img").getBoundingClientRect();
    return { width, delta: Math.abs(metadata.left - image.left), imageWidth: image.width, imageHeight: image.height, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, backSeparate: !document.querySelector("[data-card-detail-hero]").contains(document.querySelector("[data-card-back-navigation]")) };
  }, width));
  await page.close();
}
await browser.close();
console.log(JSON.stringify(report, null, 2));
