import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const BASE=process.env.BASE||"http://127.0.0.1:3130", FIXTURE_BASE=process.env.FIXTURE_BASE||"http://127.0.0.1:8011";
const ROOT=join(process.cwd(),".perf-audit","baselines",process.env.SET_VISUAL_BASELINE||"product-rankings-v1");
const all=[["desktop",{width:1440,height:900}],["tablet",{width:768,height:1024}],["mobile",{width:412,height:915}]];
const cases=process.env.ACTIVE_CASE_FILTER?all.filter(([n])=>new RegExp(process.env.ACTIVE_CASE_FILTER).test(n)):all;
const budgetMode=process.env.BUDGET_MODE==="100";
mkdirSync(ROOT,{recursive:true}); const browser=await chromium.launch(); const results={};
try { for (const [name,viewport] of cases) {
  await fetch(`${FIXTURE_BASE}/__fixture__/reset-browser`,{method:"POST"}); const context=await browser.newContext({viewport});
  await context.addCookies([{name:"token",value:"fixture-premium",url:BASE}]); const page=await context.newPage(); const errors=[]; page.on("pageerror",e=>errors.push(e.message));
  const auth=page.waitForResponse(r=>r.url().includes("/api/auth/me")&&r.status()===200,{timeout:90000}); await page.goto(`${BASE}/Rankings`,{waitUntil:"domcontentloaded",timeout:90000}); await auth;
  await page.getByRole("radio",{name:"Products",exact:true}).click(); await page.getByRole("heading",{name:"Best Products to Rip"}).waitFor({timeout:90000}); await page.waitForFunction(()=>document.body.innerText.includes("Ascended Heroes Booster Pack"),null,{timeout:90000});
  if(budgetMode){await page.getByLabel("Opening Budget").click(); await page.getByRole("option",{name:"$100",exact:true}).click(); await page.waitForFunction(()=>document.body.innerText.includes("7 units · $92.68 committed"),null,{timeout:90000});}
  await page.getByLabel("Search products or sets").fill("Ascended"); if(await page.getByText("Prismatic Evolutions Booster Pack",{exact:true}).count()) throw new Error(`${name}: search control did not filter`); await page.getByLabel("Search products or sets").fill("");
  await page.getByLabel("Sort products").click(); await page.getByRole("option",{name:"Alphabetical A–Z"}).click();
  await page.waitForLoadState("networkidle",{timeout:15000}).catch(()=>{}); const e=await page.evaluate(()=>({text:document.body.innerText,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,headers:[...document.querySelectorAll("table th")].every(x=>x.getAttribute("scope")==="col"||x.hasAttribute("aria-label")),table:!!document.querySelector("table"),ids:[...document.querySelectorAll("[id]")].map(x=>x.id).filter((x,i,a)=>a.indexOf(x)!==i)}));
  const labels=name==="mobile"?["rip score","financial","chase","collector",...(budgetMode?["7 units · $92.68 committed"]:[])]:["overall rip","financial rip","chase accessibility","collector appeal","set #21 of 22",...(budgetMode?["7 units · $92.68 committed"]:[])]; for(const label of labels){if(!e.text.toLowerCase().includes(label))throw new Error(`${name}: missing ${label}\n${e.text.slice(0,2200)}`)} if(e.text.includes("Market-Based")||e.text.includes("temporarily unavailable")||e.text.includes("O_budget")||e.text.includes("Effective Pack Efficiency"))throw new Error(`${name}: retired/unavailable copy`); if(e.overflow>1||errors.length||e.ids.length)throw new Error(`${name}: structural failure ${JSON.stringify({e,errors})}`); if(viewport.width>=768&&(!e.table||!e.headers))throw new Error(`${name}: semantic table failure`);
  const prefix=budgetMode?"budget-rankings":"product-rankings"; const screenshotPath=join(ROOT,`${prefix}__${name}.png`); await page.screenshot({path:screenshotPath,fullPage:true,animations:"disabled"}); const network=await (await fetch(`${FIXTURE_BASE}/__fixture__/report`)).json(); if(network.unexpectedBrowserRequests.length||network.unusedBrowserCriticalFixtures.length)throw new Error(`${name}: ${JSON.stringify(network)}`); results[`${prefix}__${name}`]={viewport,screenshotPath,overflow:e.overflow,network}; console.log(`accepted ${prefix}__${name}`); await context.close();
}} finally {await browser.close()} writeFileSync(join(ROOT,"acceptance.json"),`${JSON.stringify(results,null,2)}\n`);
