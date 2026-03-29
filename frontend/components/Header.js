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
  const [isTCGsDropdownOpen, setIsTCGsDropdownOpen] = useState(false);
  const [isCollectionDropdownOpen, setIsCollectionDropdownOpen] = useState(false);
  const tcgsDropdownRef = useRef(null);
  const collectionDropdownRef = useRef(null);
  const pathname = usePathname(); // Get the current route path
  const router = useRouter();

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
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <header>
      <div className="relative bg-primary text-white py-0.5">
        <div className="w-full flex items-center justify-between gap-4 px-2 md:px-6 lg:px-10">
          <div className="flex items-center min-w-0">
            <Link
              href="/"
              onClick={() => setIsMobileMenuOpen(false)}
              className="text-white cursor-pointer flex items-center gap-0 transition-all duration-300 ease-in-out hover:scale-105"
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

          <div className="flex-1 min-w-0 grid grid-cols-1 md:grid-cols-[1fr_minmax(0,32rem)_1fr] lg:grid-cols-[1fr_minmax(0,36rem)_1fr] items-center md:gap-4 lg:gap-6">
            <nav className="hidden md:flex items-center justify-end gap-4 lg:gap-5 text-[16px] font-semibold whitespace-nowrap">
              <Link
                href="/Explore"
                className={`transition-colors duration-200 ease-in-out ${
                  isTopNavActive('/Explore') ? 'text-accent' : 'hover:text-accent'
                }`}
              >
                Explore
              </Link>
              <div ref={tcgsDropdownRef} className="relative overflow-visible">
                <button
                  onClick={() => {
                    setIsTCGsDropdownOpen(!isTCGsDropdownOpen);
                    setIsCollectionDropdownOpen(false);
                  }}
                  className={`transition-colors duration-200 ease-in-out flex items-center gap-1 ${
                    isTopNavActive('/TCGs') ? 'text-accent' : 'hover:text-accent'
                  }`}
                >
                  TCGs
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-4 w-4 transition-transform duration-200 ${isTCGsDropdownOpen ? 'rotate-180' : ''}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {isTCGsDropdownOpen && (
                  <div className="absolute top-full left-1/2 -translate-x-1/2 mt-[18px] bg-primary/[0.85] text-white divide-y divide-white/30 z-50 border-b border-white/20 whitespace-nowrap min-w-fit">
                    <Link href="/TCGs/Pokemon" className="block px-6 py-4 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsTCGsDropdownOpen(false)}>
                      Pokémon
                    </Link>
                  </div>
                )}
              </div>
              <Link
                href="/Learn"
                className={`transition-colors duration-200 ease-in-out ${
                  isTopNavActive('/Learn') ? 'text-accent' : 'hover:text-accent'
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
                className="flex items-center w-full"
                inputClassName="w-full px-2.5 py-1 text-sm border border-transparent text-primary rounded-l-lg focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out"
                buttonClassName="bg-primary text-white px-3 py-1.5 rounded-r-lg hover:bg-accent transition-colors duration-200 ease-in-out flex items-center justify-center"
                placeholder="Search"
              />
            </div>

            <div className="hidden md:flex justify-start">
              <div ref={collectionDropdownRef} className="relative overflow-visible">
                <button
                  onClick={() => {
                    setIsCollectionDropdownOpen(!isCollectionDropdownOpen);
                    setIsTCGsDropdownOpen(false);
                  }}
                  className={`text-[16px] font-semibold whitespace-nowrap transition-colors duration-200 ease-in-out flex items-center gap-1 ${
                    isTopNavActive('/dashboard') ? 'text-accent' : 'hover:text-accent'
                  }`}
                >
                  My Collection
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                    className={`h-4 w-4 transition-transform duration-200 ${isCollectionDropdownOpen ? 'rotate-180' : ''}`}
                  >
                    <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {isCollectionDropdownOpen && (
                  <div className="absolute top-full left-1/2 -translate-x-1/2 mt-[18px] min-w-full w-max bg-primary/[0.85] text-white divide-y divide-white/30 z-50 border-b border-white/20 whitespace-nowrap">
                    <Link href="/dashboard/Collection" className="block px-6 py-4 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsCollectionDropdownOpen(false)}>
                      Collection
                    </Link>
                    <Link href="/dashboard/Binder" className="block px-6 py-4 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsCollectionDropdownOpen(false)}>
                      Binder
                    </Link>
                    <Link href="/dashboard/Shelf" className="block px-6 py-4 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsCollectionDropdownOpen(false)}>
                      Shelf
                    </Link>
                    <Link href="/dashboard/Watchlist" className="block px-6 py-4 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsCollectionDropdownOpen(false)}>
                      Watchlist
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center text-sm whitespace-nowrap gap-4 md:gap-5 lg:gap-6">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className="md:hidden inline-flex flex-col justify-center items-center gap-1.5 w-10 h-10"
              aria-label="Toggle menu"
              aria-expanded={isMobileMenuOpen}
              aria-controls="mobile-header-menu"
            >
              <span className={`block h-0.5 w-6 bg-white transition-transform duration-200 ${isMobileMenuOpen ? "translate-y-2 rotate-45" : ""}`} />
              <span className={`block h-0.5 w-6 bg-white transition-opacity duration-200 ${isMobileMenuOpen ? "opacity-0" : "opacity-100"}`} />
              <span className={`block h-0.5 w-6 bg-white transition-transform duration-200 ${isMobileMenuOpen ? "-translate-y-2 -rotate-45" : ""}`} />
            </button>

            <div className="hidden md:flex items-center">
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
                <>
                  {customerName ? (
                    <span className="hover:underline">Hi, {customerName}</span>
                  ) : (
                    <Link href="/dashboard" className="hover:underline">
                      Account
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {isMobileMenuOpen && (
          <div
            id="mobile-header-menu"
            className="md:hidden fixed left-0 right-0 top-[57px] bottom-0 z-40 border-t border-white/20 bg-primary/[0.85]"
            onClick={() => setIsMobileMenuOpen(false)}
          >
            <nav
              className="w-full h-full overflow-y-auto px-0 py-0 flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-4 pt-3 pb-1 text-xs font-bold tracking-[0.16em] text-white/80">EXPLORE</div>
              <div className="border-y border-white/30">
                <Link href="/Explore" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Explore
                </Link>
                <Link href="/TCGs/Pokemon" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-white/30 hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  TCGs
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-white/80">LEARN</div>
              <div className="border-y border-white/30">
                <Link href="/Learn" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Learn
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-white/80">MY COLLECTION</div>
              <div className="border-y border-white/30">
                <Link href="/dashboard/Collection" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Collection
                </Link>
                <Link href="/dashboard/Binder" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-white/30 hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Binder
                </Link>
                <Link href="/dashboard/Shelf" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-white/30 hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Shelf
                </Link>
                <Link href="/dashboard/Watchlist" className="block w-full px-4 py-3 text-[18px] font-semibold border-t border-white/30 hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                  Watchlist
                </Link>
              </div>

              <div className="px-4 pt-4 pb-1 text-xs font-bold tracking-[0.16em] text-white/80">ACCOUNT</div>
              <div className="border-y border-white/30 mb-6">
                {!isAuthenticated ? (
                  <Link href="/login" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
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
                    <Link href="/dashboard" className="block w-full px-4 py-3 text-[18px] font-semibold hover:bg-white/10 transition-colors" onClick={() => setIsMobileMenuOpen(false)}>
                      Profile
                    </Link>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="block w-full text-left px-4 py-3 text-[18px] font-semibold border-t border-white/30 hover:bg-white/10 transition-colors"
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
