import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(here, "Header.js"), "utf8").replace(/\r\n/g, "\n");

test("removed Portfolio dropdown state leaves no stale runtime references", () => {
  for (const token of [
    "isCollectionDropdownOpen",
    "setIsCollectionDropdownOpen",
    "collectionDropdownRef",
    "isMyCollectionRouteActive",
    "publicProfileHref",
    "accountUsername",
  ]) {
    assert.ok(!source.includes(token), `${token} must not survive after the Portfolio header surface is removed`);
  }
});

test("critical header account and auth controls remain present", () => {
  assert.ok(source.includes("const { user, logout } = useAuth();"), "Header must keep the canonical auth state source");
  assert.ok(source.includes("<AuthPopover"), "Login must still render AuthPopover");
  assert.ok(source.includes('href="/account-settings"'), "Account Settings must remain available");
  assert.ok(source.includes("onClick={handleLogout}"), "Logout must remain available");
  assert.ok(source.includes("<MembershipNavLink"), "Upgrade/Membership navigation must remain available");
});

test("account identity has a stable email-derived fallback", () => {
  const labelResolver = source.slice(source.indexOf("function getPreferredAccountLabel"), source.indexOf("export default function Header"));
  assert.match(labelResolver, /display_name/);
  assert.match(labelResolver, /username/);
  assert.match(labelResolver, /email/);
  assert.ok(labelResolver.indexOf("display_name") < labelResolver.indexOf("username"));
  assert.ok(labelResolver.indexOf("username") < labelResolver.indexOf("email"));
});

test("primary public navigation remains intact", () => {
  for (const destination of ["/Rankings", "/Market", "/Articles"]) {
    assert.ok(source.includes(`href="${destination}"`), `${destination} must remain in the Header`);
  }
  assert.ok(source.includes("href={TCGS_NAV_HREF}"), "TCGs navigation must remain intact");
  assert.ok(source.includes("<SearchBar"), "Search must remain present");
});
