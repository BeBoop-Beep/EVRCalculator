"use client";
import { useRouter } from "next/navigation";

export default function ProductDetailsCard({ product, addProductToCart }) {
  const router = useRouter();

  const handleProductClick = () => {
    // Convert the product object to a URL-friendly string
    const productData = encodeURIComponent(JSON.stringify(product));
    // Navigate to the product details page with the product data
    router.push(`/products/details?data=${productData}`);
  };

  const handleAddToCartClick = (e) => {
    e.stopPropagation(); // Stop event propagation
    addProductToCart(product); // Add the product to the cart
  };

  return (
    <div
      onClick={handleProductClick}
      className="group relative bg-white p-4 rounded-2xl shadow-lg hover:shadow-xl transition-all hover:cursor-pointer flex flex-col justify-between h-full"
    >
      {/* Product Image */}
      <div className="w-full h-72 bg-gray-100 rounded-lg overflow-hidden flex justify-center items-center">
        <img
          src={product.images?.[0] || "/fallback-image.jpg"}
          alt={product.title}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
        />
      </div>

      {/* Product Details */}
      <div className="mt-4 text-center">
        <h3 className="text-lg font-semibold text-gray-900">{product.title}</h3>
        <p className="text-gray-600 mt-1">${product.price}</p>
      </div>

      {/* Add to Cart Button */}
      <div className="flex justify-center mt-4">
        <button
          onClick={handleAddToCartClick}
          className="bg-black text-white rounded-lg hover:bg-gray-800 transition-colors duration-200 transform active:scale-95 w-full sm:w-auto px-8 py-4 sm:px-6 sm:py-3 md:px-8 md:py-4 lg:px-10 lg:py-2"
        >
          Add To Cart
        </button>
      </div>
    </div>
  );
}