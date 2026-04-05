function safeDecodeUriComponent(value) {
  if (typeof value !== "string") return "";

  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizeWhitespace(value) {
  return value.replace(/\s+/g, " ").trim();
}

export function normalizeUsernameForRoute(value) {
  const decoded = normalizeWhitespace(safeDecodeUriComponent(value || ""));
  const lowered = decoded.toLowerCase();
  const routeSafe = lowered
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9._-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "");

  return routeSafe || "collector";
}

function normalizeDisplayName(value) {
  if (typeof value !== "string") return "";
  return normalizeWhitespace(safeDecodeUriComponent(value));
}

function normalizeOptionalString(value) {
  if (typeof value !== "string") return "";
  return normalizeWhitespace(value);
}

export function getPublicProfileIdentity(user) {
  const userUsername = normalizeOptionalString(user?.username);
  const username = normalizeUsernameForRoute(userUsername);
  const cleanedDisplayName = normalizeDisplayName(user?.display_name ?? user?.displayName ?? "");

  const hasDisplayName = cleanedDisplayName.length > 0;
  const handle = `@${username}`;
  const displayNameForTitle = hasDisplayName ? cleanedDisplayName : null;
  const title = displayNameForTitle || handle;
  const subtitle = hasDisplayName ? handle : null;

  return {
    username,
    displayName: displayNameForTitle,
    title,
    subtitle,
    handle,
    // Backward-compatible field for existing component usage.
    secondaryHandle: subtitle,
    profileHref: `/u/${username}`,
    avatarText: (displayNameForTitle || username).slice(0, 1).toUpperCase() || "U",
  };
}

export function resolvePublicIdentity({ usernameParam, displayName }) {
  return getPublicProfileIdentity({
    username: usernameParam,
    display_name: displayName,
  });
}
