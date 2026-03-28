'use client';
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname, useRouter } from 'next/navigation'; // Use next/navigation for routing
import SearchBar from "@/components/Search/SearchBar";

export default function Header() {
  const [isAuthenticated, setIsAuthenticated] = useState(false); // Track authentication state
  const [customerName, setCustomerName] = useState(null); // Track the customer's name
  const [isClient, setIsClient] = useState(false); // Track if the component is rendered on the client
  const pathname = usePathname(); // Get the current route path
  const router = useRouter();

  const handleHeaderSearch = (query) => {
    if (!query) return;
    router.push(`/priceCheck?query=${encodeURIComponent(query)}`);
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

  return (
    <header>
      <div className="bg-primary text-white py-0.5">
        <div className="w-full flex items-center justify-between gap-4 px-2 md:px-6 lg:px-10">
          <div className="flex items-center min-w-0">
            <Link
              href="/"
              className="text-neutral-light cursor-pointer flex items-center gap-0 transition-transform duration-300 ease-in-out hover:scale-105"
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

          <div className="flex-1 flex items-center justify-center gap-4 md:gap-5 lg:gap-6 min-w-0">
            <nav className="hidden md:flex items-center gap-4 lg:gap-5 text-[15px] font-semibold whitespace-nowrap">
              <Link href="/products" className="hover:underline">
                Explore
              </Link>
              <Link href="/products" className="hover:underline">
                TCG
              </Link>
              <Link href="/products" className="hover:underline">
                Sets
              </Link>
            </nav>

            <div className="w-full max-w-md lg:max-w-lg flex items-center">
              <SearchBar
                onSearch={handleHeaderSearch}
                className="flex items-center w-full"
                inputClassName="w-full px-2.5 py-1 text-sm border border-transparent text-primary rounded-l-lg focus:outline-none"
                buttonClassName="bg-black text-white text-sm px-3 py-1 rounded-r-lg hover:bg-gray-800 transition-colors"
                placeholder="Search"
              />
            </div>

            <Link href={isAuthenticated ? "/dashboard" : "/login"} className="hidden md:inline hover:underline text-[15px] font-semibold whitespace-nowrap">
              My Collection
            </Link>
          </div>

          <div className="flex items-center text-sm whitespace-nowrap gap-4 md:gap-5 lg:gap-6">
            {!isAuthenticated ? (
              <Link href="/login" className="px-4 py-1.5 text-[15px] font-semibold border-2 border-white rounded-lg hover:bg-white hover:text-primary transition-colors">
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
    </header>
  );
}
