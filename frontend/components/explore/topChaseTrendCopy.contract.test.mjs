import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

// RipStatisticsPageClient.jsx has mixed CRLF/LF line endings, so any anchor
// that spans lines must be matched against normalized source.
const source = fs
  .readFileSync(path.join(import.meta.dirname, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

test("the Top Chase row never ships trend-source copy to users", () => {
  const forbidden = [
    "Trend source",
    "reconstructed from history",
    "window snapshot unavailable",
    "stored window snapshot was invalid",
    "history fallback.",
  ];
  for (const phrase of forbidden) {
    assert.ok(
      !source.includes(phrase),
      `RipStatisticsPageClient.jsx still renders internal trend-source copy: "${phrase}"`
    );
  }
});

test("the row delegates its only trend message to the shared helper", () => {
  assert.ok(
    source.includes("const trendStatusMessage = getTopCardTrendStatusMessage(windowState);"),
    "the message must come from getTopCardTrendStatusMessage, not an inline source ternary"
  );
  assert.ok(source.includes("getTopCardTrendStatusMessage,"), "helper must be imported");
});

test("the source distinction survives as a machine-readable attribute", () => {
  assert.ok(
    source.includes("data-trend-source={windowState.source}"),
    "diagnostics must stay available to tests/telemetry without becoming copy"
  );
});

test("development-only warning plumbing is preserved", () => {
  assert.ok(source.includes("warnForTopCardWindowState(windowState, card, selectedWindowKey);"));
  const windowState = fs
    .readFileSync(path.join(import.meta.dirname, "topChaseWindowState.mjs"), "utf8")
    .replace(/\r\n/g, "\n");
  assert.ok(
    windowState.includes('if (process.env.NODE_ENV === "production" || !windowState?.warnings?.length) return;'),
    "dev warnings must remain dev-only and intact"
  );
  assert.ok(windowState.includes('warnings.push("missing_stored_window")'));
  assert.ok(windowState.includes('reason: "malformed_stored_window"'));
});
