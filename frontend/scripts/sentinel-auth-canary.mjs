import { chromium } from "@playwright/test";

import {
  AUTH_CANARY_NAVIGATION,
  AuthCanaryError,
  authIdentityFingerprint,
  authenticatedUserFromPayload,
  loadAuthCanaryConfig,
  safeAuthCanaryConfigSummary,
  safeAuthCanaryFailure,
} from "../lib/sentinel/authCanary.mjs";


function isAuthMeResponse(response) {
  try {
    const url = new URL(response.url());
    return url.pathname === "/api/auth/me" && response.request().method() === "GET";
  } catch {
    return false;
  }
}

async function readCurrentUser(page) {
  const result = await page.evaluate(async () => {
    const response = await fetch("/api/auth/me", {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    return { status: response.status, payload };
  });
  return authenticatedUserFromPayload(result.status, result.payload);
}

async function assertRenderedAuth(page, expectedFingerprint) {
  const user = await readCurrentUser(page);
  const fingerprint = authIdentityFingerprint(user);
  if (fingerprint !== expectedFingerprint) {
    throw new AuthCanaryError("auth_canary_identity_changed");
  }

  const login = page.locator("header").getByRole("button", { name: "Login", exact: true });
  if ((await login.count()) > 0 && (await login.first().isVisible())) {
    throw new AuthCanaryError("auth_canary_header_logged_out");
  }

  const accountMenus = page.locator('header button[aria-haspopup="menu"]');
  if ((await accountMenus.count()) < 1 || !(await accountMenus.first().isVisible())) {
    throw new AuthCanaryError("auth_canary_account_menu_missing");
  }
  return fingerprint;
}

async function clickAndWaitForAuthSync(page, click, timeoutMs) {
  const [authResponse] = await Promise.all([
    page.waitForResponse(isAuthMeResponse, { timeout: timeoutMs }),
    click(),
  ]);
  return authResponse.status();
}

async function navigateViaHeader(page, destination, timeoutMs) {
  const link = page.locator("header").getByRole("link", {
    name: destination.name,
    exact: true,
  });
  if ((await link.count()) < 1) {
    throw new AuthCanaryError("auth_canary_navigation_link_missing");
  }
  const authSyncStatus = await clickAndWaitForAuthSync(
    page,
    () => link.first().click(),
    timeoutMs,
  );
  await page.waitForURL(
    (url) => url.pathname === destination.pathname || url.pathname.startsWith(`${destination.pathname}/`),
    { timeout: timeoutMs },
  );
  return authSyncStatus;
}

async function run() {
  const config = loadAuthCanaryConfig();
  let stage = "startup";
  let browser = null;
  const visited = [];
  const authSyncStatuses = [];
  const pageErrors = [];

  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1500, height: 1000 },
      baseURL: config.baseUrl,
    });
    const page = await context.newPage();
    page.setDefaultTimeout(config.timeoutMs);
    page.on("pageerror", (error) => pageErrors.push(String(error?.name || "Error")));

    stage = "login";
    const loginResponse = await context.request.post(`${config.baseUrl}/api/auth/login`, {
      data: { email: config.email, password: config.password },
      timeout: config.timeoutMs,
    });
    if (!loginResponse.ok()) {
      throw new AuthCanaryError("auth_canary_login_failed");
    }

    stage = "home";
    await page.goto(config.baseUrl, { waitUntil: "domcontentloaded", timeout: config.timeoutMs });
    const initialUser = await readCurrentUser(page);
    const expectedFingerprint = authIdentityFingerprint(initialUser);
    await assertRenderedAuth(page, expectedFingerprint);
    visited.push("/");

    for (const destination of AUTH_CANARY_NAVIGATION) {
      stage = destination.name;
      const status = await navigateViaHeader(page, destination, config.timeoutMs);
      authSyncStatuses.push({ pathname: destination.pathname, status });
      await assertRenderedAuth(page, expectedFingerprint);
      visited.push(destination.pathname);
    }

    stage = "Account Settings";
    const accountButton = page.locator('header button[aria-haspopup="menu"]').first();
    await accountButton.click();
    const accountSettings = page.getByRole("link", { name: "Account Settings", exact: true });
    if ((await accountSettings.count()) < 1) {
      throw new AuthCanaryError("auth_canary_account_settings_link_missing");
    }
    const accountStatus = await clickAndWaitForAuthSync(
      page,
      () => accountSettings.first().click(),
      config.timeoutMs,
    );
    await page.waitForURL((url) => url.pathname === "/account-settings", {
      timeout: config.timeoutMs,
    });
    authSyncStatuses.push({ pathname: "/account-settings", status: accountStatus });
    await assertRenderedAuth(page, expectedFingerprint);
    visited.push("/account-settings");

    console.log(
      JSON.stringify(
        {
          status: "passed",
          config: safeAuthCanaryConfigSummary(config),
          identityFingerprint: expectedFingerprint,
          visited,
          authSyncStatuses,
          pageErrorCount: pageErrors.length,
          pageErrorTypes: Array.from(new Set(pageErrors)).slice(0, 10),
        },
        null,
        2,
      ),
    );
    return 0;
  } catch (error) {
    console.error(JSON.stringify(safeAuthCanaryFailure(error, stage), null, 2));
    return 1;
  } finally {
    if (browser) await browser.close();
  }
}

process.exitCode = await run();
