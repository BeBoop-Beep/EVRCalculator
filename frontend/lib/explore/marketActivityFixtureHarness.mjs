// Explicit acceptance/dev authority. Product code defaults to no Activity
// capability and no transport. Keep this module out of normal page imports.
export const FMA3_FIXTURE_ID = "fma_fixture_11";

export const FMA3_FIXTURE_CAPABILITIES = Object.freeze({
  demandPressure: Object.freeze({}),
  fairValue: Object.freeze({}),
  activity: Object.freeze({
    "*": Object.freeze({
      available: true,
      marketKey: "set:fixture-modern-set",
      activityGenerationId: "7c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
      rosterRef: Object.freeze({
        generationId: "5f0c7a52-3b1e-4b8e-9a51-2d7c1f0e9a10",
        kind: "SURFACE_V2_GENERATION",
        marketKey: "set:fixture-modern-set",
      }),
      evidenceFingerprint: "a4ad86cfb6d5c14fb1f5b273a1306fdb0bc19e4e471caa5d2769bca8baff3fd3",
      asOf: "2026-09-29",
      windowDays: 30,
      tier: "RAW",
    }),
  }),
});
