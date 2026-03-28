"use client";
import { useRouter } from "next/navigation";

export default function ProductDetailsCard({ product }) {
  const router = useRouter();

  const handleProductClick = () => {
    const productData = encodeURIComponent(JSON.stringify(product));
    router.push(`/products/details?data=${productData}`);
  };

  return (
    <div
      onClick={handleProductClick}
      className="group relative bg-white p-4 rounded-2xl shadow-lg hover:shadow-xl transition-all hover:cursor-pointer"
    >
      {/* Product Image */}
      <div className="w-full h-96 bg-gray-100 rounded-lg overflow-hidden flex justify-center items-center"> {/* Increased height */}
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
    </div>
  );
}