import assert from "node:assert/strict"; import test from "node:test";
import {annualPricingSummary,formatMinorAmount,planPricingSummary} from "./billingPricing.mjs";
const offers=[
  {offerKey:"plus_monthly",plan:"plus",billingInterval:"month",unitAmount:999,currency:"usd",purchasable:true},
  {offerKey:"plus_annual",plan:"plus",billingInterval:"year",unitAmount:7900,currency:"usd",purchasable:true},
  {offerKey:"premium_monthly",plan:"premium",billingInterval:"month",unitAmount:2499,currency:"usd",purchasable:true},
  {offerKey:"premium_annual",plan:"premium",billingInterval:"year",unitAmount:21900,currency:"usd",purchasable:true}];
test("approved offer minor amounts remain exact",()=>assert.deepEqual(Object.fromEntries(offers.map(x=>[x.offerKey,x.unitAmount])),{plus_monthly:999,plus_annual:7900,premium_monthly:2499,premium_annual:21900}));
test("Plus annual savings and rounded public discount are exact",()=>{const r=annualPricingSummary(offers[0],offers[1]);assert.equal(r.annualSavings,4088);assert.equal(r.annualDiscountPercent,34);assert.equal(r.effectiveMonthlyAnnualRate,658);});
test("Premium annual savings and rounded public discount are exact",()=>{const r=annualPricingSummary(offers[2],offers[3]);assert.equal(r.annualSavings,8088);assert.equal(r.annualDiscountPercent,27);assert.equal(r.effectiveMonthlyAnnualRate,1825);});
test("pricing derives only from trusted purchasable DTO offers",()=>{const r=planPricingSummary({offers:[...offers,{offerKey:"evil",unitAmount:1,currency:"usd",purchasable:false}]},"plus");assert.equal(r.monthly.unitAmount,999);assert.equal(r.annual.unitAmount,7900);assert.equal(formatMinorAmount(r.annualSummary.annualSavings,"usd"),"$40.88");});
