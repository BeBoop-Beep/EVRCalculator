import { expect, test } from "@playwright/test";

for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
  test(`anonymous Era and Set score views stay locked without fetching at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    let scorecardRequests = 0;
    page.on("request", (request) => {
      if (request.url().includes("/rankings/scorecards")) scorecardRequests += 1;
    });
    await page.goto("http://127.0.0.1:3015/Rankings", { waitUntil: "networkidle" });
    await expect(page.locator("body")).not.toHaveText("");
    await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
    await page.getByRole("radio", { name: "Sets", exact: true }).click();
    await expect(page.getByText("Benchmark Set Rankings are available with Index Plus or Premium.")).toBeVisible();
    await page.getByRole("radio", { name: "Eras", exact: true }).click();
    await expect(page.getByText("Era Rankings are available with Index Plus or Premium.")).toBeVisible();
    expect(scorecardRequests).toBe(0);
  });

  test(`Plus scorecards render and tabs reuse payloads at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const calls = { set: 0, era: 0 };
    const metric = (score, rank, cohortSize = 2) => ({ score, rank, cohortSize, tier: score >= 5 ? "A" : "C", benchmarkReferenceScore: 5, deltaVsBenchmark: score - 5, benchmarkPosition: score > 5 ? "above" : score < 5 ? "below" : "at" });
    const setRows = [
      { entityId: "s1", name: "Alpha Set", canonicalKey: "alpha-set", era: { eraId: "e1", eraName: "Alpha Era" }, overall: metric(7.2, 1), financial: metric(6.8, 1), collector: metric(5.7, 1), chase: metric(4.8, 2) },
      { entityId: "s2", name: "Beta Set", canonicalKey: "beta-set", era: { eraId: "e2", eraName: "Beta Era" }, overall: metric(4.4, 2), financial: metric(4.1, 2), collector: metric(4.7, 2), chase: metric(6.3, 1) },
    ];
    const eraRows = [
      { entityId: "e1", name: "Alpha Era", canonicalKey: "alpha-era", modeledSetCount: 6, overall: metric(6.4, 1), financial: metric(6.1, 1), collector: metric(5.8, 1), chase: metric(5.3, 1) },
      { entityId: "e2", name: "Beta Era", canonicalKey: "beta-era", modeledSetCount: 4, overall: metric(4.3, 2), financial: metric(4.5, 2), collector: metric(4.2, 2), chase: metric(4.1, 2) },
    ];
    await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "plus-fixture", email: "plus@example.test", index_plan: "plus" } }) }));
    await page.route("**/api/tcgs/pokemon/rankings/scorecards?entity_type=*", (route) => {
      const entityType = new URL(route.request().url()).searchParams.get("entity_type");
      calls[entityType] += 1;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "available", entityType, marketDate: "2026-09-28", rows: entityType === "set" ? setRows : eraRows }) });
    });
    await page.goto("http://127.0.0.1:3015/Rankings", { waitUntil: "networkidle" });
    await page.getByRole("radio", { name: "Sets", exact: true }).click();
    await expect(page.getByPlaceholder("Search Sets…")).toBeVisible();
    await expect(page.locator("[data-rankings-reference-row]:visible")).toHaveCount(1);
    for (const tab of ["Financial", "Collector", "Chase", "RIP Score"]) {
      await page.getByRole("button", { name: tab, exact: true }).click();
      await expect(page.getByPlaceholder("Search Sets…")).toBeVisible();
    }
    expect(calls.set).toBe(1);
    await page.getByRole("radio", { name: "Eras", exact: true }).click();
    await expect(page.getByPlaceholder("Search Eras…")).toBeVisible();
    if (viewport.width >= 768) await expect(page.getByRole("columnheader", { name: "Modeled Sets" })).toBeVisible();
    else await expect(page.getByRole("columnheader", { name: "Modeled Sets" })).toBeHidden();
    await expect(page.locator("[data-rankings-reference-row]:visible")).toHaveCount(1);
    expect(calls.era).toBe(1);
    await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  });
}
