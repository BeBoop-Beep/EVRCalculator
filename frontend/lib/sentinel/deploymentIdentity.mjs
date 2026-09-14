function clean(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

export function buildDeploymentIdentity(env = process.env) {
  const build = clean(
    env.VERCEL_GIT_COMMIT_SHA || env.GIT_SHA || env.SOURCE_VERSION || "development",
  );
  const ref = clean(env.VERCEL_GIT_COMMIT_REF || env.GIT_BRANCH || "");
  const environment = clean(env.VERCEL_ENV || env.NODE_ENV || "development");
  const provider = env.VERCEL === "1" ? "vercel" : "local";

  return {
    status: "ok",
    build: String(build || "development").slice(0, 40),
    ref,
    environment,
    provider,
  };
}
