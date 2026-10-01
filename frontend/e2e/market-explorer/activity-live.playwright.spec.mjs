import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, pickRow } from "./helpers.mjs";

const base = process.env.EXPLORER_LIVE_ACTIVITY_URL || "http://127.0.0.1:3304";
const backend = process.env.EXPLORER_FIXTURE_BACKEND_URL || "http://127.0.0.1:8301";
const output = path.resolve(process.cwd(), "../backend/artifacts/market_activity_v1/fma4");
const shot = async (page, name) => { fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true }); };
const backendRequests = async () => (await fetch(`${backend}/__fixture/requests`)).json();

test("live transport through Next proxies: Plus group, constituents, detail, and bounded request counts", async ({ browser }) => {
  await fetch(`${backend}/__fixture/reset`);
  const { context, page, net } = await newSession(browser, { base, plan: "plus", viewport: { width: 1440, height: 900 } });
  await openExplorer(page, base);
  await pickRow(page, "sets", "Fossil");
  const cardChip = page.locator("[data-market-explorer-active-chip]", { hasText: "Fossil" });
  await cardChip.locator("[data-market-explorer-active-focus]").click();
  const activityMode = page.locator("[data-market-chart-view='activity']");
  await expect(activityMode).toHaveAttribute("data-market-chart-view-state", "available");
  await activityMode.click();
  await expect(page.locator("[data-market-activity-chart]")).toBeVisible();
  await expect(page.locator("[data-market-activity-pane]")).toHaveCount(0);
  const beforeHover = net.requests.length;
  await page.locator("[data-market-performance-chart]").hover();
  expect(net.requests.length).toBe(beforeHover);
  await shot(page, "1440x900-live-group-sales");

  await page.locator("[data-market-explorer-view-details]").click();
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(page.locator("[data-market-constituents-activity]")).toBeVisible();
  await shot(page, "1440x900-live-constituents-activity");
  await page.locator("[data-market-constituents-activity] tbody button").first().click();
  await expect(page.locator("[data-market-activity-instrument]")).toBeVisible();
  await expect(page.locator("[data-market-activity-instrument]")).toContainText("Peer context");
  await shot(page, "1440x900-live-instrument-detail");

  const requests = await backendRequests();
  const count = (route) => requests.filter((entry) => entry.route === route).length;
  expect(count("/market/explorer/activity/capabilities")).toBe(1);
  expect(count("/market/explorer/activity")).toBe(1);
  expect(count("/market/explorer/activity/constituents")).toBe(1);
  expect(count("/market/explorer/activity/instrument")).toBe(1);
  await context.close();
});

test("Basic remains unavailable and mobile live Activity cards are compact", async ({ browser }) => {
  const basic = await newSession(browser, { base, viewport: { width: 1440, height: 900 } });
  await openExplorer(basic.page, base);
  await basic.page.locator("[data-market-explorer-active-focus]").first().click();
  await expect(basic.page.locator("[data-market-chart-view='activity']")).toHaveAttribute("data-market-chart-view-state", "locked");
  await shot(basic.page, "1440x900-basic-activity-locked");
  await basic.context.close();

  const mobile = await newSession(browser, { base, plan: "plus", viewport: { width: 390, height: 844 }, mobile: true });
  await openExplorer(mobile.page, base);
  await pickRow(mobile.page, "sets", "Fossil");
  await mobile.page.locator("[data-market-explorer-active-chip]", { hasText: "Fossil" }).locator("[data-market-explorer-active-focus]").click();
  await mobile.page.locator("[data-market-chart-view='activity']").click();
  await expect(mobile.page.locator("[data-market-activity-chart]")).toBeVisible();
  await shot(mobile.page, "390x844-live-activity");
  await mobile.context.close();
});
