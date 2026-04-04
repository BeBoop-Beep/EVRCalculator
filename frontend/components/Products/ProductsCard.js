"use client";
import { useRouter } from "next/navigation";
import Image from "next/image";

export default function ProductDetailsCard({ product, addProductToCart }) {
  const router = useRouter();

  const handleProductClick = () => {
    const productId = product?._id || product?.id;
    if (!productId) return;
    router.push(`/sealed-products/${encodeURIComponent(String(productId))}`);
  };

  const handleAddToCartClick = (e) => {
    e.stopPropagation(); // Stop event propagation
    addProductToCart(product); // Add the product to the cart
  };

  return (
    <div
      onClick={handleProductClick}
      className="group relative bg-[var(--surface-panel)] p-4 rounded-2xl border border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-all hover:cursor-pointer flex flex-col justify-between h-full"
    >
      {/* Product Image */}
      <div className="w-full h-72 bg-[var(--surface-page)] rounded-lg overflow-hidden flex justify-center items-center">
        <Image
          unoptimized
          src={product.images?.[0] || "/fallback-image.jpg"}
          alt={product.title}
          width={1200}
          height={1200}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
        />
      </div>

      {/* Product Details */}
      <div className="mt-4 text-center">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">{product.title}</h3>
        <p className="text-[var(--text-secondary)] mt-1">${product.price}</p>
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