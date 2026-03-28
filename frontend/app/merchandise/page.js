"use client";
import { CartContext } from "@/components/Cart/CartContext";
import MerchandiseStoreFilterWrapper from "@/components/Merchandise/MerchandiseStoreFilter/MerchandiseStoreFilterWrapper";
import MerchandiseCard from "@/components/Merchandise/MerchandiseCard"; // Import the new component
import Spinner from "@/utils/Spinner";
import { useContext, useEffect, useState } from "react";

export default function Merchandise() {
  const [merchandise, setMerchandise] = useState([]);
  const [filteredMerchandise, setFilteredMerchandise] = useState([]);
  const { addItem } = useContext(CartContext);
  const [selectedChildCategories, setSelectedChildCategories] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isFilterOpen, setIsFilterOpen] = useState(false); // Set to false initially

  useEffect(() => {
    async function fetchMerchandise() {
      try {
        const res = await fetch("/api/merchandise");
        if (!res.ok) {
          throw new Error("Failed to fetch merchandise");
        }
        const data = await res.json();
        setMerchandise(data);
        setFilteredMerchandise(data);
      } catch (error) {
        console.error("Error fetching merchandise:", error);
      }
    }
    fetchMerchandise();
  }, []);

  useEffect(() => {
    async function fetchCategories() {
      try {
        const res = await fetch("/api/category");
        if (!res.ok) {
          throw new Error("Failed to fetch categories");
        }
        const data = await res.json();
        setCategories(data);
      } catch (error) {
        console.error("Error fetching categories:", error);
      }
    }
    fetchCategories();
  }, []);

  useEffect(() => {
    if (selectedChildCategories.length === 0) {
      setFilteredMerchandise(merchandise);
    } else {
      const filtered = merchandise.filter((item) =>
        selectedChildCategories.some((catId) =>
          item.categories.includes(catId.toString())
        )
      );
      setFilteredMerchandise(filtered);
    }
  }, [selectedChildCategories, merchandise]);

  useEffect(() => {
    setTimeout(() => {
      document.body.classList.add("loaded");
    }, 50);
  }, []);

  function addProductToCart(merch) {
    if (merch && merch._id) {
      addItem(merch._id);
    } else {
      console.error("Product object or _id is missing!");
    }
  }

  const handleFilterChange = (selectedChildCategories) => {
    setSelectedChildCategories(selectedChildCategories);
  };

  const toggleFilter = () => {
    setIsFilterOpen((prev) => !prev);
  };

  if (merchandise.length === 0) {
    return <Spinner />;
  }

  return (
    <div className="container mx-auto px-6 py-10">
      <div className="flex space-x-8">
        {isFilterOpen && (
          <div className="w-64 flex-shrink-0">
            <MerchandiseStoreFilterWrapper
              onFilterChange={handleFilterChange}
              categories={categories}
            />
          </div>
        )}

        <div className={`flex-grow ${isFilterOpen ? "" : "w-full"}`}>
          <div className="flex w-full mb-6 items-center justify-center">
            <h2 className="text-3xl font-bold text-gray-900 text-center mr-4">
              Shiny Merch
            </h2>
            <div className="relative group">
              <button
                onClick={toggleFilter}
                className="p-2 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                aria-label="Toggle filters"
              >
                {isFilterOpen ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                ) : (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 6h16M4 12h16M4 18h16"
                    />
                  </svg>
                )}
              </button>
              <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-1.5 bg-gray-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                Filters
                <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-gray-800 rotate-45"></div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {filteredMerchandise.length > 0 ? (
              filteredMerchandise.map((merch, index) => (
                <MerchandiseCard
                  key={index}
                  merch={merch}
                  addProductToCart={addProductToCart}
                />
              ))
            ) : (
              <div className="col-span-full text-center text-gray-500">
                No merchandise found under those filters at this time.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}