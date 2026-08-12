// §11 content verification: Top Chase, movers, sealed, charts must all render.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3101";
const SETS = {
  ascendedHeroes: "Ascended Heroes",
  shroudedFable: "Shrouded Fable",
  prismaticEvolutions: "Prismatic Evolutions",
  scarletAndViolet151: "151",
};

const browser = await chromium.launch();
try {
  for (const [slug, name] of Object.entries(SETS)) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    let topChaseReqs = 0;
    page.on("request", (r) => {
      if (/\/market\/top-chase/.test(r.url())) topChaseReqs += 1;
    });

    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${slug}?tab=market`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(14000);

    const r = await page.evaluate(() => {
      const t = document.body.innerText;
      const sec = document.querySelector("#set-detail-market-top-chase, [data-market-page]");
      const scope = sec || document.body;
      return {
        awaitingTrend: (t.match(/Awaiting trend/gi) || []).length,
        unableToLoad: /unable to load|request timed out|could not be read/i.test(t),
        retryButtons: [...document.querySelectorAll("button")].filter((b) => /retry/i.test(b.textContent || "")).length,
        svgCharts: scope.querySelectorAll("svg.recharts-surface").length,
        sealedHeading: /sealed/i.test(t),
        moversHeading: /movers|heating|cooling/i.test(t),
        setValueHeading: /set value/i.test(t),
        priceCells: (t.match(/\$[\d,]+\.\d{2}/g) || []).length,
      };
    });

    console.log(
      `${name.padEnd(22)} topChaseRequests=${topChaseReqs}  awaitingTrend=${r.awaitingTrend}  charts=${r.svgCharts}  ` +
        `prices=${r.priceCells}  retryBtns=${r.retryButtons}  unableToLoad=${r.unableToLoad}  ` +
        `sealed=${r.sealedHeading} movers=${r.moversHeading} setValue=${r.setValueHeading}`
    );
    await ctx.close();
  }
} finally {
  await browser.close();
}
