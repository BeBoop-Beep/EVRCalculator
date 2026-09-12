export function createFixtureConsumption(manifest) {
  const preflight = new Map();
  const browser = new Map();
  const unexpectedPreflightRequests = [];
  const unexpectedBrowserRequests = [];

  const record = (route, { phase = "browser", expected = true, method = "GET" } = {}) => {
    const target = phase === "preflight" ? preflight : browser;
    target.set(route, (target.get(route) || 0) + 1);
    if (!expected) {
      (phase === "preflight" ? unexpectedPreflightRequests : unexpectedBrowserRequests)
        .push(`${method} ${route}`);
    }
  };

  const entries = (values) => [...values.entries()].map(([route, count]) => ({ route, count }));
  const report = () => {
    const critical = Object.entries(manifest.routes || {}).filter(([, entry]) => entry.critical !== false);
    return {
      preflightRequests: entries(preflight),
      browserRequests: entries(browser),
      unexpectedPreflightRequests: [...unexpectedPreflightRequests],
      unexpectedBrowserRequests: [...unexpectedBrowserRequests],
      unusedBrowserCriticalFixtures: critical.filter(([route]) => !browser.has(route)).map(([route]) => route),
    };
  };

  const resetBrowser = () => {
    browser.clear();
    unexpectedBrowserRequests.length = 0;
  };

  return { record, report, resetBrowser };
}
