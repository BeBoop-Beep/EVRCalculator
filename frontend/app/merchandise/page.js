"use client";
import { useEffect } from "react";

export default function Merchandise() {
  useEffect(() => {
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  return (
    <div className="container mx-auto px-6 py-10">
      <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-md p-8 text-center">
        <h2 className="text-3xl font-bold text-gray-900 mb-4">Shiny Merch</h2>
        <p className="text-gray-600">
          Merchandise is currently unavailable in the frontend while this section is being migrated.
        </p>
      </div>
    </div>
  );
}