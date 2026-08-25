import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source=fs.readFileSync(path.resolve("components/explore/ProductFamilyRankingsClient.jsx"),"utf8");
const page=fs.readFileSync(path.resolve("app/Explore/page.js"),"utf8");

test("Products defaults to a real Overall table, not Coming Soon",()=>{assert.ok(source.includes('next==="products"?"overall":"sets"'));assert.ok(source.includes("OverallProductRankings"));assert.ok(!source.includes("Coming Soon"));assert.ok(page.includes("overallProductRankings={payload?.overallProductRankings}"));});
test("Overall defaults to dynamic Full Market and offers one budget DarkSelect",()=>{assert.ok(source.includes("overallProductRankings?.defaultBudgetKey"));assert.ok(source.includes("overall.fullMarketBudget"));assert.ok(!source.includes("1350"));assert.ok(source.includes('<DarkSelect ariaLabel="Opening Budget"'));assert.equal((source.match(/ariaLabel="Opening Budget"/g)||[]).length,1);});
test("canonical budget options arrive from the published projection, not frontend bands",()=>{assert.ok(source.includes("overall?.availableBudgets"));for(const hardcoded of ['"$25"','"$50"','"$100"','"$150"','"$250"','"$500"'])assert.ok(!source.includes(hardcoded));});
test("Overall fields retain persisted budget semantics",()=>{for(const field of ["p.budgetRank","p.budgetTier","p.overallRipScore","p.financialRipScore",'overall?"unitPrice"',"p.expectedValue",'overall?"chanceToRecoverCapital"',"p.quantity","p.actualCommittedCapital"])assert.ok(source.includes(field),field);assert.ok(source.includes("committed"));});
test("Format Strength remains natural within-family context",()=>{for(const field of ["p?.familyRank","p?.familySize","p?.familyTier"])assert.ok(source.includes(field),field);});
test("search and alternate sort preserve the stored rank",()=>{assert.ok(source.includes("filterAndSortProducts"));assert.ok(source.includes("a.budgetRank||a.familyRank"));assert.ok(source.includes("#{rank(p)}"));});
test("Overall and family views share one product table presentation",()=>{assert.equal((source.match(/function ProductRankingsTable/g)||[]).length,1);assert.equal((source.match(/<table className=/g)||[]).length,1);assert.ok(source.includes("overall?\"Unit Price\":\"Market Price\""));assert.ok(source.includes("<TableSearchInput"));});
test("mobile shares rank, strategy, RIP badge and tier",()=>{assert.ok(source.includes('className="space-y-2 p-3 md:hidden"'));assert.ok(source.includes("<Strategy p={p}"));assert.ok(source.includes("compact/><RipTierMark"));});
test("Overall remains first in product subnav",()=>{const nav=source.slice(source.indexOf('<nav aria-label="Product family"'),source.indexOf('</nav>'));assert.ok(nav.indexOf('>Overall</button>')<nav.indexOf("entries.map"));});
