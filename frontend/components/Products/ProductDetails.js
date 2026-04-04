"use client";
import { useState, useContext } from "react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Navigation, Pagination } from "swiper/modules";
import "swiper/css";
import "swiper/css/navigation";
import "swiper/css/pagination";
import { CartContext } from "@/components/Cart/CartContext"; // Import CartContext
import Image from "next/image";

export default function ProductDetails({ product }) {
  const [selectedVariant, setSelectedVariant] = useState(product.variants?.[0]);
  const { addItem } = useContext(CartContext); // Use CartContext

  // Function to handle adding the product to the cart
  const handleAddToCart = () => {
    if (product && product._id) {
      addItem(product._id); // Add the product to the cart
    } else {
      console.error("Product object or _id is missing!");
    }
  };

  return (
    <div className="min-h-screen bg-[var(--surface-page)] py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Increased the width and height of the container */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 bg-[var(--surface-panel)] p-12 rounded-lg border border-[var(--border-subtle)]" style={{ minHeight: '600px' }}>
          {/* Product Image Gallery */}
          <div className="flex justify-center items-center">
            <Swiper
              modules={[Navigation, Pagination]}
              navigation
              pagination={{ clickable: true }}
              spaceBetween={10}
              slidesPerView={1}
              className="w-full max-w-lg" // Increased max-width
            >
              {(selectedVariant?.image ? [selectedVariant.image] : product.images).map(
                (image, index) => (
                  <SwiperSlide key={index}>
                    <Image
                      unoptimized
                      src={image || "/fallback-image.jpg"}
                      alt={product.title}
                      width={1200}
                      height={500}
                      className="w-full h-[500px] object-cover rounded-lg" // Increased height
                    />
                  </SwiperSlide>
                )
              )}
            </Swiper>
          </div>

          {/* Product Details Section */}
          <div className="space-y-6">
            <h1 className="text-3xl font-bold text-[var(--text-primary)]">{product.title}</h1>
            <p className="text-xl text-[var(--text-secondary)]">${product.price}</p>
            <p className="text-[var(--text-secondary)]">{product.description}</p>

            {/* Variants */}
            {product.variants && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-[var(--text-primary)]">Select Variant</h3>
                <div className="flex flex-wrap gap-2">
                  {product.variants.map((variant) => (
                    <button
                      key={variant._id}
                      onClick={() => setSelectedVariant(variant)}
                      className={`px-4 py-2 border rounded-lg ${
                        selectedVariant?._id === variant._id
                          ? "bg-[var(--surface-header)] text-[var(--text-primary)]"
                          : "bg-[var(--surface-page)] text-[var(--text-secondary)]"
                      } hover:bg-[var(--surface-hover)] transition-colors`}
                    >
                      {variant.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Add to Cart Button */}
            <button
              onClick={handleAddToCart} // Use the handleAddToCart function
              className="w-full bg-black text-white px-6 py-3 rounded-lg hover:bg-gray-800 transition-colors duration-200 transform active:scale-95"
            >
              Add To Cart
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}