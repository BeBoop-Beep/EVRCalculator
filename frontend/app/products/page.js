"use client";
import { CartContext } from "@/components/Cart/CartContext";
import ProductStoreFilterWrapper from "@/components/Products/ProductStoreFilter/ProductStoreFilterWrapper";
import ProductsCard from "@/components/Products/ProductsCard";
import { useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function Products() {
  const [products, setProducts] = useState([]);
  const [filteredProducts, setFilteredProducts] = useState([]);
  const { addItem } = useContext(CartContext);
  const [selectedChildCategories, setSelectedChildCategories] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const router = useRouter();

  // Fetch all products from the server when the component mounts
  useEffect(() => {
    async function fetchProducts() {
      try {
        const res = await fetch("/api/product");
        if (!res.ok) {
          throw new Error("Failed to fetch products");
        }
        const data = await res.json();
        setProducts(data);
        setFilteredProducts(data);
      } catch (error) {
        console.error("Error fetching products:", error);
      }
    }
    fetchProducts();
  }, []);

  // Fetch all categories from the server when the component mounts
  useEffect(() => {
    setCategories([]);
  }, []);

  // Filter products when selected child categories change
  useEffect(() => {
    if (selectedChildCategories.length === 0) {
      setFilteredProducts(products);
    } else {
      const filtered = products.filter((product) =>
        selectedChildCategories.some((catId) =>
          product.categories.includes(catId.toString())
        )
      );
      setFilteredProducts(filtered);
    }
  }, [selectedChildCategories, products]);

  // Add product to cart
  function addProductToCart(product) {
    if (product && product._id) {
      addItem(product._id);
    } else {
      console.error("Product object or _id is missing!");
    }
  }

  // Handle filter change (selected child categories)
  const handleFilterChange = (selectedChildCategories) => {
    setSelectedChildCategories(selectedChildCategories);
  };

  // Toggle filter visibility
  const toggleFilter = () => {
    setIsFilterOpen((prev) => !prev);
  };

  const handleProductClick = (product) => {
    // Convert the product object to a URL-friendly string
    const productData = encodeURIComponent(JSON.stringify(product));
    // Navigate to the product details page with the product data
    router.push(`/products/details?data=${productData}`);
  };

  return (
    <div className="container mx-auto px-6 py-10">
      {/* Flex container for filter and products */}
      <div className="flex space-x-8">
        {/* Filter Wrapper Component (conditionally rendered) */}
        {isFilterOpen && (
          <div className="w-64 flex-shrink-0">
            <ProductStoreFilterWrapper
              onFilterChange={handleFilterChange}
              categories={categories}
            />
          </div>
        )}

        {/* Product Listing */}
        <div className={`flex-grow ${isFilterOpen ? "" : "w-full"}`}>
          <div className="flex w-full mb-6 items-center justify-center">
            <h2 className="text-3xl font-bold text-gray-900 text-center mr-4">
              The Shiny Shop
            </h2>
            {/* Filter Toggle Button with Tooltip */}
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
              {/* Tooltip */}
              <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-1.5 bg-gray-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                Filters
                <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-gray-800 rotate-45"></div>
              </div>
            </div>
          </div>

          {/* Product Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {filteredProducts.length > 0 ? (
              filteredProducts.map((product, index) => (
                <div
                  key={index}
                  onClick={() => handleProductClick(product)}
                  className="cursor-pointer"
                >
                  <ProductsCard
                    product={product}
                    addProductToCart={addProductToCart}
                  />
                </div>
              ))
            ) : (
              <div className="col-span-full text-center text-gray-500">
                No products found under those filters at this time.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}