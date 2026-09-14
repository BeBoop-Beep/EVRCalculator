import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3130";
const FIXTURE_BASE = process.env.FIXTURE_BASE || "http://127.0.0.1:8011";
const ROOT = join(process.cwd(), ".perf-audit", "baselines", process.env.SET_VISUAL_BASELINE || "product-detail-v1");
const all = [["desktop",{width:1440,height:900}],["tablet",{width:768,height:1024}],["mobile",{width:412,height:915}]];
const cases = process.env.ACTIVE_CASE_FILTER ? all.filter(([name]) => new RegExp(process.env.ACTIVE_CASE_FILTER).test(name)) : all;
const id = "c29f8489-22db-4ad0-9022-c1a40e503f14";
mkdirSync(ROOT,{recursive:true});
const browser=await chromium.launch(); const results={};
try {
  for (const [name,viewport] of cases) {
    await fetch(`${FIXTURE_BASE}/__fixture__/reset-browser`,{method:"POST"});
    const context=await browser.newContext({viewport});
    await context.addCookies([{name:"token",value:"fixture-premium",url:BASE}]);
    const page=await context.newPage(); const errors=[]; page.on("pageerror",e=>errors.push(e.message));
    const auth=page.waitForResponse(r=>r.url().includes("/api/auth/me")&&r.status()===200,{timeout:90000});
    await page.goto(`${BASE}/sealed-products/${id}`,{waitUntil:"domcontentloaded",timeout:90000}); await auth;
    await page.locator('[data-product-rip-section]').waitFor({timeout:90000});
    await page.locator('[data-product-chase-intelligence] [data-chase-primary-metric]').waitFor({timeout:90000});
    await page.waitForLoadState("networkidle",{timeout:15000}).catch(()=>{});
    const evidence=await page.evaluate(()=>{
      const image=document.querySelector('[data-product-image]'); const text=document.body.innerText;
      return {text,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
        image:{exists:Boolean(image),src:image?.getAttribute('src'),alt:image?.getAttribute('alt'),source:image?.getAttribute('data-product-image-source')},
        placeholder:Boolean(document.querySelector('[data-product-image-placeholder]')),
        ripUnavailable:Boolean(document.querySelector('[data-product-rip-unavailable]')),
        chaseBad:Boolean(document.querySelector('[data-chase-state="error"],[data-chase-state="unavailable"],[data-chase-state="authority-unavailable"],[data-chase-state="auth-required"],[data-chase-state="plan-upgrade-required"]')),
        evState:document.querySelector('[data-ev-realization-card]')?.getAttribute('data-ev-realization-state'),
        unnamed:[...document.querySelectorAll('button,a')].filter(n=>!n.getAttribute('aria-label')&&!n.textContent?.trim()).length,
        duplicateIds:[...document.querySelectorAll('[id]')].map(n=>n.id).filter((x,i,a)=>a.indexOf(x)!==i)};
    });
    for(const expected of ["ascended heroes booster pack","overall rip","financial rip","this product","chase accessibility","parent set","collector appeal","product chase intelligence","7 products","$92.68","$7.32","ev realization"]){if(!evidence.text.toLowerCase().includes(expected))throw new Error(`${name}: missing ${expected}\n${evidence.text.slice(0,2200)}`)}
    if(evidence.ripUnavailable||evidence.chaseBad)throw new Error(`${name}: false unavailable/error state`);
    if(evidence.evState!=="available")throw new Error(`${name}: EV Realization ${evidence.evState}`);
    if(evidence.overflow>1)throw new Error(`${name}: overflow ${evidence.overflow}px`);
    if(!evidence.image.exists||evidence.image.src!=="/images/pokemon/booster-packs/ascendedHeroes.webp"||evidence.image.source!=="local"||evidence.placeholder)throw new Error(`${name}: image DOM ${JSON.stringify(evidence.image)}`);
    if(evidence.image.alt!=="Ascended Heroes Booster Pack sealed product")throw new Error(`${name}: image alt ${evidence.image.alt}`);
    if(evidence.unnamed||evidence.duplicateIds.length||errors.length)throw new Error(`${name}: accessibility/errors ${JSON.stringify({unnamed:evidence.unnamed,duplicateIds:evidence.duplicateIds,errors})}`);
    const screenshotPath=join(ROOT,`product-rip__${name}.png`); await page.screenshot({path:screenshotPath,fullPage:true,animations:"disabled"});
    const network=await(await fetch(`${FIXTURE_BASE}/__fixture__/report`)).json(); if(network.unexpectedBrowserRequests.length||network.unusedBrowserCriticalFixtures.length)throw new Error(`${name}: network ${JSON.stringify(network)}`);
    results[`product-rip__${name}`]={viewport,screenshotPath,overflow:evidence.overflow,image:evidence.image,network}; console.log(`accepted product-rip__${name}`); await context.close();
  }
} finally {await browser.close();}
writeFileSync(join(ROOT,"acceptance.json"),`${JSON.stringify(results,null,2)}\n`);
