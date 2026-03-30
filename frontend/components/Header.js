'use client';
import Link from "next/link";
import { useState, useEffect, useRef } from "react";
import { usePathname, useRouter } from 'next/navigation'; // Use next/navigation for routing
import SearchBar from "@/components/Search/SearchBar";
import Image from "next/image";

export default function Header() {
  const [isAuthenticated, setIsAuthenticated] = useState(false); // Track authentication state
  const [customerName, setCustomerName] = useState(null); // Track the customer's name
  const [isClient, setIsClient] = useState(false); // Track if the component is rendered on the client
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isUserDropdownOpen, setIsUserDropdownOpen] = useState(false);
  const [isTCGsDropdownOpen, setIsTCGsDropdownOpen] = useState(false);
  const [isCollectionDropdownOpen, setIsCollectionDropdownOpen] = useState(false);
  const tcgsDropdownRef = useRef(null);
  const collectionDropdownRef = useRef(null);
  const userDropdownRef = useRef(null);
  const pathname = usePathname(); // Get the current route path
  const router = useRouter();

  const navTabBase = "min-w-[96px] xl:min-w-[110px] px-3 xl:px-4 py-2 text-sm xl:text-[15px] font-medium text-center rounded-md transition-colors duration-200 ease-in-out";
  const navTabActive = "text-[var(--accent)] relative after:content-[''] after:absolute after:left-4 after:right-4 after:-bottom-1 after:h-[2px] after:rounded-full after:bg-[var(--accent)]";
  const navTabInactive = "text-[var(--text-secondary)] hover:text-[var(--accent)]";
  const navDropdownSurface = "bg-[var(--surface-panel)]";
  const navDropTrigger = "inline-flex items-center gap-1.5 px-2 py-2 text-sm xl:text-[15px] font-medium leading-5 rounded-md border border-transparent transition-colors duration-200 ease-in-out";
  const navDropPanel = `absolute top-full mt-1 rounded-md ${navDropdownSurface} text-[var(--text-primary)] z-50 border border-[var(--border-subtle)] whitespace-nowrap py-1`;
  const navDropPanelCompact = "w-36";
  const navDropPanelAccount = "w-48";
  const navDropItem = "block w-full px-4 py-2 text-[15px] leading-5 text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors";
  const navDropTriggerOpen = "text-[var(--accent)] bg-[var(--surface-header)]";
  const navDropTriggerClosed = "text-[var(--text-secondary)] bg-[var(--surface-header)] hover:text-[var(--accent)] hover:bg-[var(--surface-hover)]";

  const isTopNavActive = (path) => pathname === path || pathname.startsWith(`${path}/`);

  const handleHeaderSearch = (query) => {
    if (!query) return;
    router.push(`/priceCheck?query=${encodeURIComponent(query)}`);
  };

  const handleLogout = () => {
    const logoutUser = async () => {
      try {
        await fetch('/api/logout', {
          method: 'POST',
          credentials: 'include',
        });
      } catch (error) {
        // Continue local cleanup even if API logout fails.
      }

      setIsAuthenticated(false);
      setCustomerName(null);
      setIsMobileMenuOpen(false);
      setIsUserDropdownOpen(false);
      router.push('/login');
    };

    logoutUser();
  };

  useEffect(() => {
    setIsClient(true); // Set isClient to true on client-side rendering
  }, []);

  useEffect(() => {
    if (!isClient) return; // Wait for client-side rendering

    // Function to check authentication status
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/auth/me', {
          credentials: 'include',
        });

        if (res.ok) {
          const customer = await res.json();
          setIsAuthenticated(true);
          setCustomerName(customer.user?.name || null);
        } else {
          setIsAuthenticated(false);
          setCustomerName(null);
        }
      } catch (error) {
        setIsAuthenticated(false);
        setCustomerName(null);
      }
    };

    // Check if we're on the login or signup page, or need to check authentication
    if (pathname === '/login' || pathname === '/signup') {
      setIsAuthenticated(false); // Set to false on login/signup pages
    } else {
      checkAuth(); // Perform the authentication check for other pages
    }
  }, [pathname, isClient]); // Dependency on pathname and isClient

  useEffect(() => {
    setIsMobileMenuOpen(false);
    setIsTCGsDropdownOpen(false);
    setIsCollectionDropdownOpen(false);
    setIsUserDropdownOpen(false);
  }, [pathname]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        tcgsDropdownRef.current &&
        !tcgsDropdownRef.current.contains(event.target)
      ) {
        setIsTCGsDropdownOpen(false);
      }

      if (
        collectionDropdownRef.current &&
        !collectionDropdownRef.current.contains(event.target)
      ) {
        setIsCollectionDropdownOpen(false);
      }

      if (
        userDropdownRef.current &&
        !userDropdownRef.current.contains(event.target)
      ) {
        setIsUserDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <header>
      <div className="relative text-[var(--text-primary)] py-1">
        <div className="w-full flex items-center justify-between gap-3 lg:gap-4 px-2 sm:px-4 lg:px-6 xl:px-10">
          <div className="flex items-center min-w-0 mr-6">
            <Link
              href="/"
              onClick={() => setIsMobileMenuOpen(false)}
              className="text-[var(--text-primary)] cursor-pointer flex items-center gap-0 transition-all duration-300 ease-in-out hover:scale-105"
            >
              <Image
                src="/images/inDex.png"
                alt="inDex"
                width={58}
                height={58}
                className="h-[52px] w-[52px] md:h-[58px] md:w-[58px] object-contain"
              />
              <span className="hidden sm:inline -ml-1 text-xl md:text-2xl font-semibold tracking-tight">
                inDex
              </span>
            </Link>

          </div>

          <div className="flex-1 min-w-0 grid grid-cols-1 lg:grid-cols-[1fr_minmax(0,22rem)_1fr] xl:grid-cols-[1fr_minmax(0,30rem)_1fr] items-center lg:gap-4 xl:gap-6">
            <nav className="hidden lg:flex items-center justify-end gap-2.5 xl:gap-4 whitespace-nowrap">
              <Link
                href="/Explore"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTopNavActive('/Explore') ? navTabActive : navTabInactive
                }`}
              >
                Explore
              </Link>
              <div ref={tcgsDropdownRef} className="relative">
                <button
                  onClick={() => {
                    setIsTCGsDropdownOpen(!isTCGsDropdownOpen);
                    setIsCollectionDropdownOpen(false);
                  }}
                  className={`${navDropTrigger} ${isTopNavActive('/TCGs') || isTCGsDropdownOpen ? navDropTriggerOpen : navDropTriggerClosed}`}
                  aria-expanded={isTCGsDropdownOpen}
                  aria-haspopup="menu"
                >
                  TCGs
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-3.5 w-3.5 opacity-60 transition-transform duration-200 ${isTCGsDropdownOpen ? 'rotate-180' : ''}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {isTCGsDropdownOpen && (
                  <div className={`${navDropPanel} ${navDropPanelCompact} left-1/2 -translate-x-1/2`}>
                    <Link href="/TCGs/Pokemon" className={navDropItem} onClick={() => setIsTCGsDropdownOpen(false)}>
                      Pokémon
                    </Link>
                  </div>
                )}
              </div>
              <Link
                href="/Learn"
                className={`${navTabBase} inline-flex items-center justify-center ${
                  isTopNavActive('/Learn') ? navTabActive : navTabInactive
                }`}
              >
                Learn
              </Link>
            </nav>

            <div
              className="w-full flex items-center justify-self-center"
              onClickCapture={() => setIsMobileMenuOpen(false)}
              onFocusCapture={() => setIsMobileMenuOpen(false)}
            >
              <SearchBar
                onSearch={handleHeaderSearch}
                className="relative flex items-center w-full lg:w-[360px] xl:w-[420px]"
                inputClassName="w-full px-4 py-2 pr-12 rounded-lg bg-[var(--surface-panel)] border border-[var(--border-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                buttonClassName="absolute right-1 top-1/2 -translate-y-1/2 p-2 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors duration-200 ease-in-out flex items-center justify-center"
                placeholder="Search"
              />
            </div>

            <div className="hidden lg:flex justify-start">
              <div ref={collectionDropdownRef} className="relative">
                <button
                  onClick={() => {
                    setIsCollectionDropdownOpen(!isCollectionDropdownOpen);
                    setIsTCGsDropdownOpen(false);
                  }}
                  className={`${navDropTrigger} ${isTopNavActive('/dashboard') || isCollectionDropdownOpen ? navDropTriggerOpen : navDropTriggerClosed}`}
                  aria-expanded={isCollectionDropdownOpen}
                  aria-haspopup="menu"
                >
                  My Collection
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-3.5 w-3.5 opacity-60 transition-transform duration-200 ${isCollectionDropdownOpen ? 'rotate-180' : ''}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {isCollectionDropdownOpen && (
                  <div className={`${navDropPanel} ${navDropPanelCompact} left-1/2 -translate-x-1/2`}>
                    <Link href="/dashboard/Collection" className={navDropItem} onClick={() => setIsCollectionDropdownOpen(false)}>
                      Collection
                    </Link>
                    <Link href="/dashboard/Binder" className={navDropItem} onClick={() => setIsCollectionDropdownOpen(false)}>
                      Binder
                    </Link>
                    <Link href="/dashboard/Shelf" className={navDropItem} onClick={() => setIsCollectionDropdownOpen(false)}>
                      Shelf
                    </Link>
                    <Link href="/dashboard/Watchlist" className={navDropItem} onClick={() => setIsCollectionDropdownOpen(false)}>
                      Watchlist
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center text-sm whitespace-nowrap gap-3 lg:gap-4 xl:gap-6">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className="lg:hidden inline-flex flex-col justify-center items-center gap-1.5 w-10 h-10"
              aria-label="Toggle menu"
              aria-expanded={isMobileMenuOpen}
              aria-controls="mobile-header-menu"
            >
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-transform duration-200 ${isMobileMenuOpen ? "translate-y-2 rotate-45" : ""}`} />
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-opacity duration-200 ${isMobileMenuOpen ? "opacity-0" : "opacity-100"}`} />
              <span className={`block h-0.5 w-6 bg-[var(--text-primary)] transition-transform duration-200 ${isMobileMenuOpen ? "-translate-y-2 -rotate-45" : ""}`} />
            </button>

            <div className="hidden lg:flex items-center">
              {!isAuthenticated ? (
                <Link href="/login" className="pl-4 pr-2.5 py-2 text-[16px] font-semibold border-2 border-brand rounded-xl bg-brand text-white hover:bg-brand-dark hover:border-brand-dark transition-colors duration-200 ease-in-out">
                  <span className="inline-flex items-center gap-1">
                    Login
                    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
                      <path d="M11 4.5H14.25C15.2165 4.5 16 5.2835 16 6.25V13.75C16 14.7165 15.2165 15.5 14.25 15.5H11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M4 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M9.5 7.5L12 10L9.5 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </Link>
              ) : (
                <div ref={userDropdownRef} className="relative">
                  <button
                    type="button"
                    onClick={() => setIsUserDropdownOpen((prev) => !prev)}
                    className={`${navDropTrigger} ${navDropPanelAccount} justify-between ${isTopNavActive('/profile') || isTopNavActive('/account-settings') || isUserDropdownOpen ? navDropTriggerOpen : navDropTriggerClosed}`}
                    aria-expanded={isUserDropdownOpen}
                    aria-haspopup="menu"
                  >
                    <span className="truncate">{customerName || "Account"}</span>
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
                        href="/profile"
                        className={navDropItem}
                        onClick={() => setIsUserDropdownOpen(false)}
                      >
                        Profile
                      </Link>
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
            className="lg:hidden absolute left-0 right-0 top-full z-40 border-t border-[var(--border-subtle)] bg-[var(--surface-panel)] max-h-[calc(100vh-var(--app-header-offset,57px))] overflow-y-auto"
            onClick={() => setIsMobileMenuOpen(false)}
          >
            <nav
              className="w-full px-0 py-0 flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-4 pt-3 pb-1 text-xs font-bold tracking-[0.16em] text-[var(--text-secondary)]">EXPLORE</div>
              <div className="border-y border-[var(--border-subtle)]">
                <Link href="/Explore" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Explore
                </Link>
                <Link href="/TCGs/Pokemon" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  TCGs
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-[var(--text-secondary)]">LEARN</div>
              <div className="border-y border-[var(--border-subtle)]">
                <Link href="/Learn" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Learn
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-[var(--text-secondary)]">MY COLLECTION</div>
              <div className="border-y border-[var(--border-subtle)]">
                <Link href="/dashboard/Collection" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Collection
                </Link>
                <Link href="/dashboard/Binder" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Binder
                </Link>
                <Link href="/dashboard/Shelf" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Shelf
                </Link>
                <Link href="/dashboard/Watchlist" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Watchlist
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-[var(--text-secondary)]">ACCOUNT</div>
              <div className="border-y border-[var(--border-subtle)] mb-6">
                {!isAuthenticated ? (
                  <Link href="/login" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                    <span className="inline-flex items-center gap-1">
                      Login
                      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-5 w-5">
                        <path d="M11 4.5H14.25C15.2165 4.5 16 5.2835 16 6.25V13.75C16 14.7165 15.2165 15.5 14.25 15.5H11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M4 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M9.5 7.5L12 10L9.5 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                  </Link>
                ) : (
                  <>
                    <Link href="/profile" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                      Profile
                    </Link>
                    <Link href="/account-settings" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
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
