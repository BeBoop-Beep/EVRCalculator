'use client';
import Link from "next/link";
import { useState, useEffect, useRef } from "react";
import { usePathname, useRouter } from 'next/navigation'; // Use next/navigation for routing
import SearchBar from "@/components/Search/SearchBar";
import Image from "next/image";
import { useAuth } from "@/components/AuthContext";
import { TCGS_NAV_HREF, isTopNavRouteActive } from "@/lib/navigation/tcgsNav.mjs";
import AuthPopover from "@/components/AuthPopover";
import MembershipNavLink from "@/components/membership/MembershipNavLink";

function getCleanText(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function getPreferredAccountLabel(user) {
  const displayName = getCleanText(user?.display_name ?? user?.displayName);
  if (displayName) return displayName;

  const username = getCleanText(user?.username);
  if (username) return username;

  return null;
}

export default function Header() {
  // Auth state derives from AuthContext — single source of truth.
  // Header no longer polls /api/auth/me independently on every navigation.
  const { user, logout } = useAuth();
  const isAuthenticated = !!user;
  const accountLabel = getPreferredAccountLabel(user);

  const [isClient, setIsClient] = useState(false); // Track if the component is rendered on the client
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isUserDropdownOpen, setIsUserDropdownOpen] = useState(false);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const userDropdownRef = useRef(null);
  const authRef = useRef(null);
  const mobileAuthRef = useRef(null);
  const authTriggerRef = useRef(null);
  const pathname = usePathname(); // Get the current route path
  const router = useRouter();

  const avatarLetter = (accountLabel || "A").charAt(0).toUpperCase();

  const navTabBase = "px-3 xl:px-4 py-2 text-sm xl:text-[15px] font-medium text-center rounded-md transition-[color,background-color,opacity] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.65)]";
  const navTabActive = "text-[rgb(45,212,191)] relative after:content-[''] after:absolute after:left-4 after:right-4 after:-bottom-1 after:h-[2px] after:rounded-full after:bg-[rgb(45,212,191)]";
  const navTabInactive = "text-[var(--text-secondary)] opacity-85 hover:text-[var(--text-primary)] hover:opacity-100";
  // Border, background and shadow all come from the shared dropdown glass so
  // the header menus read as the same material as the set-page dropdowns.
  const navDropdownSurface = "set-dropdown-glass";
  const navDropTrigger = "inline-flex items-center gap-1.5 px-2 py-2 text-sm xl:text-[15px] font-medium leading-5 rounded-md border border-transparent transition-[color,background-color,opacity] duration-150 ease-out";
  const navDropPanel = `absolute top-full mt-1 rounded-xl ${navDropdownSurface} text-[var(--text-primary)] z-[1100] whitespace-nowrap py-1 dropdown-enter`;
  const navDropPanelCompact = "w-36";
  const navDropPanelAccount = "w-48";
  const navDropItem = "set-dropdown-option block w-full px-4 py-2 text-[15px] leading-5 text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors";
  const navDropTriggerOpen = "text-[var(--text-primary)] bg-[var(--surface-hover)]";
  const navDropTriggerClosed = "text-[var(--text-secondary)] bg-[var(--surface-header)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]";
  const navDropTriggerActive = "relative text-[rgb(45,212,191)] after:content-[''] after:absolute after:left-2 after:right-2 after:-bottom-1 after:h-[2px] after:rounded-full after:bg-[rgb(45,212,191)]";

  const isTopNavActive = (path) => isTopNavRouteActive(pathname, path);
  const isTcgsRouteActive = isTopNavActive('/TCGs');

  const handleHeaderSearch = (query) => {
    if (!query) return;
    router.push(`/priceCheck?query=${encodeURIComponent(query)}`);
  };

  const handleLogout = () => {
    setIsMobileMenuOpen(false);
    setIsUserDropdownOpen(false);
    logout();
  };

  const closeAuth = () => {
    setIsAuthOpen(false);
    requestAnimationFrame(() => authTriggerRef.current?.focus());
  };

  useEffect(() => {
    setIsClient(true); // Set isClient to true on client-side rendering
  }, []);

  useEffect(() => {
    setIsMobileMenuOpen(false);
    setIsCollectionDropdownOpen(false);
    setIsUserDropdownOpen(false);
    setIsAuthOpen(false);
  }, [pathname]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        userDropdownRef.current &&
        !userDropdownRef.current.contains(event.target)
      ) {
        setIsUserDropdownOpen(false);
      }
      if (
        isAuthOpen &&
        !authRef.current?.contains(event.target) &&
        !mobileAuthRef.current?.contains(event.target)
      ) setIsAuthOpen(false);
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape" && isAuthOpen) closeAuth();
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isAuthOpen]);

  return (
    <header className="relative z-[1000]">
      <div className="relative text-[var(--text-primary)] py-1">
        <div className="w-full min-w-0 max-w-full relative flex items-center gap-2 px-2 sm:px-4 lg:px-6 xl:px-10">
          <div className="flex shrink-0 items-center sm:mr-3 lg:mr-6">
            <Link
              href="/"
              onClick={() => setIsMobileMenuOpen(false)}
              className="text-[var(--text-primary)] cursor-pointer flex items-center gap-1.5 transition-all duration-300 ease-in-out hover:scale-105"
            >
              <Image
                src="/images/inDex.png"
                alt="inDex"
                width={58}
                height={58}
                priority
                fetchPriority="high"
                sizes="(max-width: 768px) 50px, 56px"
                className="h-[50px] w-[50px] md:h-[56px] md:w-[56px] object-contain"
              />
              <span className="hidden sm:flex items-center -ml-1 md:-ml-2 leading-none">
                <span className="text-[20px] md:text-[26px] font-semibold text-[#097754]">
                  in
                </span>
                <span className="text-[20px] md:text-[26px] font-semibold text-white">
                  Dex
                </span>
              </span>
            </Link>

          </div>

          <div className="hidden xl:block flex-1" />

          <div
            className="xl:hidden flex flex-1 min-w-0 items-center"
            onClickCapture={() => setIsMobileMenuOpen(false)}
            onFocusCapture={() => setIsMobileMenuOpen(false)}
          >
            <SearchBar
              onSearch={handleHeaderSearch}
              className="relative flex items-center w-full min-w-0"
              inputClassName="w-full min-w-0 px-3 py-2 pr-10 rounded-lg bg-[var(--surface-panel)] border border-[var(--border-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] text-sm"
              buttonClassName="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors duration-200 ease-in-out flex items-center justify-center"
              placeholder="Search"
            />
          </div>

          <div className="absolute right-[calc(50%+260px)] 2xl:right-[calc(50%+280px)] top-1/2 hidden -translate-y-1/2 xl:flex items-center">
            <nav className="flex items-center gap-4 whitespace-nowrap">
              <Link
                href="/Rankings"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTopNavActive('/Rankings') || isTopNavActive('/Explore') ? navTabActive : navTabInactive
                }`}
              >
                Rankings
              </Link>
              <Link
                href="/Market"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTopNavActive('/Market') ? navTabActive : navTabInactive
                }`}
              >
                Market
              </Link>
              {/* Pokémon is the only live TCG, so TCGs is a direct link to its
                  Sets catalog rather than a one-item menu. It stays active for
                  every /TCGs route. */}
              <Link
                href={TCGS_NAV_HREF}
                aria-current={isTcgsRouteActive ? "page" : undefined}
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTcgsRouteActive ? navTabActive : navTabInactive
                }`}
              >
                TCGs
              </Link>
              <Link
                href="/Articles"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTopNavActive('/Articles') ? navTabActive : navTabInactive
                }`}
              >
                Articles
              </Link>
            </nav>
          </div>

          <div
            className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 xl:flex items-center"
            onClickCapture={() => setIsMobileMenuOpen(false)}
            onFocusCapture={() => setIsMobileMenuOpen(false)}
          >
            <SearchBar
              onSearch={handleHeaderSearch}
              className="relative flex items-center w-full min-w-0 max-w-full lg:w-[360px] xl:w-[420px]"
              inputClassName="w-full min-w-0 px-4 py-2 pr-12 rounded-lg bg-[var(--surface-panel)] border border-[var(--border-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:border-[rgb(45,212,191)] focus:ring-2 focus:ring-[rgba(45,212,191,0.35)]"
              buttonClassName="absolute right-1 top-1/2 -translate-y-1/2 p-2 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors duration-200 ease-in-out flex items-center justify-center"
              placeholder="Search"
            />
          </div>

          <div className="flex shrink-0 items-center text-sm whitespace-nowrap gap-2 sm:gap-3 lg:gap-4 xl:gap-6">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className="xl:hidden inline-flex flex-col justify-center items-center gap-1.5 w-10 h-10"
              aria-label="Toggle menu"
              aria-expanded={isMobileMenuOpen}
              aria-controls="mobile-header-menu"
            >
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-transform duration-200 ${isMobileMenuOpen ? "translate-y-2 rotate-45" : ""}`} />
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-opacity duration-200 ${isMobileMenuOpen ? "opacity-0" : "opacity-100"}`} />
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-transform duration-200 ${isMobileMenuOpen ? "-translate-y-2 -rotate-45" : ""}`} />
            </button>

            <div className="hidden xl:flex items-center">
              <MembershipNavLink />
              <span className="w-2" aria-hidden="true" />
              {!isAuthenticated ? (
                <div ref={authRef} className="relative">
                <button ref={authTriggerRef} type="button" onClick={() => setIsAuthOpen((value) => !value)} aria-expanded={isAuthOpen} aria-haspopup="dialog" className="pl-4 pr-2.5 py-2 text-[16px] font-semibold border-2 border-brand rounded-xl bg-brand text-white hover:bg-brand-dark hover:border-brand-dark transition-colors duration-200 ease-in-out">
                  <span className="inline-flex items-center gap-1">
                    Login
                    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
                      <path d="M11 4.5H14.25C15.2165 4.5 16 5.2835 16 6.25V13.75C16 14.7165 15.2165 15.5 14.25 15.5H11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M4 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M9.5 7.5L12 10L9.5 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </button>
                {isAuthOpen && <AuthPopover onClose={closeAuth} />}
                </div>
              ) : (
                <div ref={userDropdownRef} className="relative">
                  <button
                    type="button"
                    onClick={() => setIsUserDropdownOpen((prev) => !prev)}
                    className={`${navDropTrigger} ${navDropPanelAccount} justify-between ${(isTopNavActive('/account-settings') || isUserDropdownOpen) ? navDropTriggerOpen : navDropTriggerClosed}`}
                    aria-expanded={isUserDropdownOpen}
                    aria-haspopup="menu"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-[11px] font-bold text-white">
                      {avatarLetter}
                    </span>
                    <span className="truncate">{accountLabel || "Account"}</span>
                    <svg
                      viewBox="0 0 20 20"
                      fill="none"
                      aria-hidden="true"
                      className={`h-3.5 w-3.5 opacity-60 transition-transform duration-200 ${isUserDropdownOpen ? 'rotate-180' : ''}`}
                    >
                      <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>

                  {isUserDropdownOpen && (
                    <div className={`${navDropPanel} ${navDropPanelAccount} left-1/2 -translate-x-1/2`}>
                      <Link
                        href="/account-settings"
                        className={navDropItem}
                        onClick={() => setIsUserDropdownOpen(false)}
                      >
                        Account Settings
                      </Link>
                      <button
                        type="button"
                        onClick={handleLogout}
                        className={`${navDropItem} w-full text-left`}
                      >
                        Logout
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {isMobileMenuOpen && (
          <div
            id="mobile-header-menu"
            className="xl:hidden absolute left-0 right-0 top-full z-[1000] border-t border-[var(--border-subtle)] bg-[var(--surface-panel)] max-h-[calc(100vh-var(--app-header-offset,57px))] overflow-y-auto"
            onClick={() => setIsMobileMenuOpen(false)}
          >
            <nav
              className="w-full px-0 py-0 flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-[var(--text-secondary)]">ACCOUNT</div>
              <div className="border-y border-[var(--border-subtle)] mb-6">
                <MembershipNavLink mobile />
                {!isAuthenticated ? (
                  <div ref={mobileAuthRef} className="px-3 py-3">
                    <button type="button" onClick={() => setIsAuthOpen((value) => !value)} className="block w-full px-4 py-3 text-left text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors">
                      <span className="inline-flex items-center gap-1">
                        Login
                        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
                          <path d="M11 4.5H14.25C15.2165 4.5 16 5.2835 16 6.25V13.75C16 14.7165 15.2165 15.5 14.25 15.5H11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M4 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M9.5 7.5L12 10L9.5 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                    </button>
                    {isAuthOpen && <div className="mt-2"><AuthPopover embedded onClose={() => setIsAuthOpen(false)} /></div>}
                  </div>
                ) : (
                  <>
                    <Link href="/account-settings" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                      Account Settings
                    </Link>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="block w-full text-left px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors"
                    >
                      Logout
                    </button>
                  </>
                )}
              </div>
            </nav>
          </div>
        )}
      </div>
    </header>
  );
}
