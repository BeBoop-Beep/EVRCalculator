import { chromium } from "playwright";

const BASE = "http://localhost:3000";

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  const results = {};

  await page.goto(`${BASE}/TCGs/Pokemon/Sets/ascendedHeroes?tab=market`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector('[data-top-chase-row]', { timeout: 45000 });
  await page.waitForTimeout(500);

  // --- CARDS LENS ---
  const rows = await page.$$('[data-top-chase-row]');
  results.rowCount = rows.length;

  if (rows.length >= 2) {
    // Click row 1 (select, no nav)
    await rows[0].click();
    await page.waitForTimeout(400);
    results.cardsFirstClickUrl = page.url();

    // Click row 1 again (should navigate)
    const rowsAfter = await page.$$('[data-top-chase-row]');
    await rowsAfter[0].click();
    await page.waitForTimeout(1200);
    results.cardsSecondClickUrl = page.url();
    await page.goBack({ waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-top-chase-row]', { timeout: 45000 });
    await page.waitForTimeout(500);

    // Now select row 2 (different card), confirm no nav
    const rowsBack = await page.$$('[data-top-chase-row]');
    await rowsBack[1].click();
    await page.waitForTimeout(400);
    results.cardsSelectRow2Url = page.url();
    const viewCardHref = await page.$eval('[data-top-chase-view-card]', (el) => el.getAttribute("href")).catch(() => null);
    const nameHref = await page.$$eval('a', (as) => as.map((a) => a.href)).catch(() => []);
    results.cardsViewCardHref = viewCardHref;
  }

  // --- SEALED LENS ---
  const sealedTab = await page.$('button[role="tab"]:has-text("Sealed")');
  if (sealedTab) {
    await sealedTab.click();
    await page.waitForTimeout(2500);
    const sealedRows = await page.$$('[data-top-chase-row]');
    results.sealedRowCount = sealedRows.length;
    if (sealedRows.length >= 1) {
      await sealedRows[0].click();
      await page.waitForTimeout(400);
      results.sealedFirstClickUrl = page.url();
      const viewProductHref = await page.$eval('[data-top-chase-view-card]', (el) => el.getAttribute("href")).catch(() => null);
      results.sealedViewProductHref = viewProductHref;

      const rowsAfter = await page.$$('[data-top-chase-row]');
      await rowsAfter[0].click();
      await page.waitForTimeout(1200);
      results.sealedSecondClickUrl = page.url();
    }
  }

  console.log(JSON.stringify(results, null, 2));
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
