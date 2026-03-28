"use client";

import { useState, useEffect } from "react";
import NavBar from "@/components/NavBar";
import Header from "@/components/Header";

export default function StickyNav() {
  const [isVisible, setIsVisible] = useState(true);
  let lastScrollY = 0;

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;

      if (currentScrollY < lastScrollY) {
        setIsVisible(true); // Scrolling up → Show navbar & header
      } else {
        setIsVisible(false); // Scrolling down → Hide navbar & header
      }

      lastScrollY = currentScrollY;
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div
      className={`fixed top-0 left-0 w-full bg-white transition-transform duration-300 z-50 ${
        isVisible ? "translate-y-0 shadow-lg" : "-translate-y-full"
      }`}
    >
      <Header />
      <NavBar />
    </div>
  );
}
