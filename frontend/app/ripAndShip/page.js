"use client";
import { useEffect } from "react";

export default function RipAndShip() {
  useEffect(() => {
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  return (
    <div className="container mx-auto px-6 py-10">
      <div className="max-w-2xl mx-auto bg-[var(--surface-panel)] rounded-lg border border-[var(--border-subtle)] p-8 text-center">
        <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-4">Rip And Ship</h2>
        <p className="text-[var(--text-secondary)]">
          Rip &amp; Ship items are currently unavailable in the frontend while this section is being migrated.
        </p>
      </div>
    </div>
  );
}
