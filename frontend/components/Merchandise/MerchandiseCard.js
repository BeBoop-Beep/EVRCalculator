"use client";
import Image from "next/image";

export default function MerchandiseCard({ merch, addProductToCart }) {
  return (
    <div className="group relative bg-white p-4 rounded-2xl shadow-lg hover:shadow-xl transition-all hover:cursor-pointer flex flex-col justify-between h-full">
      <a
        href={merch.url}
        target="_blank"
        rel="noopener noreferrer"
        className="w-full block"
      >
        {/* Product Image */}
        <div className="w-full h-72 bg-gray-100 rounded-lg overflow-hidden flex justify-center items-center">
          <Image
            unoptimized
            src={merch.images?.[0] || "/fallback-image.jpg"}
            alt={merch.title}
            width={720}
            height={720}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
          />
        </div>

        {/* Product Details */}
        <div className="mt-4 text-center">
          <h3 className="text-lg font-semibold text-gray-900">{merch.title}</h3>
          <p className="text-gray-600 mt-1">${merch.price}</p>
        </div>
      </a>

      {/* Add to Cart Button */}
      <div className="mt-4 text-center">
        <button
          onClick={(e) => {
            e.preventDefault(); // Prevent default link behavior
            addProductToCart(merch); // Add the product to the cart
          }}
          className="bg-black text-white rounded-lg hover:bg-gray-800 transition-colors duration-200 transform active:scale-95 w-full sm:w-auto px-8 py-4 sm:px-6 sm:py-3 md:px-8 md:py-4 lg:px-10 lg:py-2"
        >
          Add To Cart
        </button>
      </div>
    </div>
  );
}