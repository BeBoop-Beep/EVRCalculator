'use client';
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from 'next/navigation'; // Use next/navigation for routing

export default function Header() {
  const [isHovered, setIsHovered] = useState(false); // Track hover state
  const [isAuthenticated, setIsAuthenticated] = useState(false); // Track authentication state
  const [customerName, setCustomerName] = useState(null); // Track the customer's name
  const [isClient, setIsClient] = useState(false); // Track if the component is rendered on the client
  const pathname = usePathname(); // Get the current route path  

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
    <header className="shadow">
      <div className="bg-primary text-white py-2">
        <div className="container mx-auto flex justify-between items-center px-4">
          {/* Logo and Store Name */}
          <div className="flex items-center logo-container">
            <Link
              href="/"
              className="text-3xl font-bold text-neutral-light cursor-pointer flex justify-content items-center space-x-0 w-100"
              onMouseEnter={() => setIsHovered(true)} // Set hover state
              onMouseLeave={() => setIsHovered(false)} // Reset hover state
            >
              <div className="logo h-16 w-auto overflow-hidden">
                <img
                  src={isHovered
                    ? "/images/shinyFindsLogoHoverFour.png"
                    : "/images/shinyFindsLogoFour.png"}
                  alt="Shiny Finds Logo"
                  className="h-full w-full object-contain transition-transform duration-300 ease-in-out"
                  style={{
                    transform: isHovered ? "scale(1.1)" : "scale(1)",
                    transition: "transform 1.0s ease-in-out",
                  }}
                />
              </div>
              <span
                style={{
                  transform: isHovered ? "scale(1.1)" : "scale(1)",
                  transition: "transform 0.2s ease-in-out",
                }}
              >
                Shiny Finds
              </span>
            </Link>
          </div>

          {/* Conditional navigation links */}
          <div className="text-sm space-x-4">
            {!isAuthenticated ? (
              <>
                <Link href="/login" className="hover:underline">
                  Login
                </Link>
                <Link href="/signup" className="hover:underline">
                  Sign Up
                </Link>
              </>
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
