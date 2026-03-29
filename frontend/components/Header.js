'use client';
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname, useRouter } from 'next/navigation'; // Use next/navigation for routing
import SearchBar from "@/components/Search/SearchBar";

export default function Header() {
  const [isAuthenticated, setIsAuthenticated] = useState(false); // Track authentication state
  const [customerName, setCustomerName] = useState(null); // Track the customer's name
  const [isClient, setIsClient] = useState(false); // Track if the component is rendered on the client
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isTCGsDropdownOpen, setIsTCGsDropdownOpen] = useState(false);
  const pathname = usePathname(); // Get the current route path
  const router = useRouter();

  const isTopNavActive = (path) => pathname === path || pathname.startsWith(`${path}/`);

  const handleHeaderSearch = (query) => {
    if (!query) return;
    router.push(`/priceCheck?query=${encodeURIComponent(query)}`);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setIsAuthenticated(false);
    setCustomerName(null);
    setIsMobileMenuOpen(false);
    router.push('/login');
  };

  useEffect(() => {
    setIsClient(true); // Set isClient to true on client-side rendering
  }, []);

  useEffect(() => {
    if (!isClient) return; // Wait for client-side rendering

    // Function to check authentication status
    const checkAuth = async () => {
      try {
        const token = localStorage.getItem("token"); // Get token from localStorage

        // Token exists and is valid, fetch user details
        const res = await fetch('/api/auth/me', {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (res.ok) {
          const customer = await res.json();
          setIsAuthenticated(true);
          setCustomerName(customer.name || null);
        } else {
          setIsAuthenticated(false);
          localStorage.removeItem("token"); // Remove invalid token
        }
      } catch (error) {
        setIsAuthenticated(false);
        localStorage.removeItem("token"); // Ensure to remove invalid token in case of error
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
  }, [pathname]);

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
              <img
                src="/images/inDex.png"
                alt="inDex"
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
              <div className="relative overflow-visible">
                <button
                  onClick={() => setIsTCGsDropdownOpen(!isTCGsDropdownOpen)}
                  className={`transition-colors duration-200 ease-in-out flex items-center gap-1 ${
                    isTopNavActive('/TCGs') ? 'text-accent' : 'hover:text-accent'
                  }`}
                >
                  TCGs
                  <span className={`text-sm transition-transform ${isTCGsDropdownOpen ? 'rotate-180' : ''}`}>▼</span>
                </button>
                {isTCGsDropdownOpen && (
                  <div className="absolute top-full left-1/2 -translate-x-1/2 mt-3 bg-primary/60 text-white divide-y divide-white/30 z-50 border-b border-white/20 whitespace-nowrap min-w-fit">
                    <Link href="/TCGs/Pokemon" className="block px-4 py-3 hover:bg-white/10 transition-colors font-semibold" onClick={() => setIsTCGsDropdownOpen(false)}>
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
              <Link
                href={isAuthenticated ? "/dashboard" : "/login"}
                className="text-[16px] font-semibold whitespace-nowrap transition-colors duration-200 ease-in-out hover:text-accent"
              >
                My Collection
              </Link>
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
                <Link href="/login" className="px-4 py-1.5 text-[15px] font-semibold border-2 border-brand rounded-lg bg-brand text-white hover:bg-brand-dark hover:border-brand-dark transition-colors duration-200 ease-in-out">
                  Login
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
            className="md:hidden fixed left-0 right-0 top-[57px] bottom-0 z-40 border-t border-white/20 bg-primary/60"
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
                    Login
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
