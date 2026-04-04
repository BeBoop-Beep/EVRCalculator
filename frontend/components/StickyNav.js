"use client";

import { useEffect, useRef } from "react";
import Header from "@/components/Header";

export default function StickyNav() {
  const navShellRef = useRef(null);

  useEffect(() => {
    const updateHeaderOffset = () => {
      const currentHeight = navShellRef.current?.offsetHeight;
      if (!currentHeight) return;
      document.documentElement.style.setProperty("--app-header-offset", `${currentHeight}px`);
    };

    updateHeaderOffset();

    const resizeObserver = new ResizeObserver(() => {
      updateHeaderOffset();
    });

    if (navShellRef.current) {
      resizeObserver.observe(navShellRef.current);
    }

    window.addEventListener("resize", updateHeaderOffset);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateHeaderOffset);
    };
  }, []);

  return (
    <div
      ref={navShellRef}
      className="sticky top-0 z-50 w-full bg-[var(--surface-header)] border-b border-[var(--border-subtle)]"
    >
      <Header />
    </div>
  );
}
