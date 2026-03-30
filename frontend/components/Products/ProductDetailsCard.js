"use client";
import { useRouter } from "next/navigation";
import Image from "next/image";

export default function ProductDetailsCard({ product }) {
  const router = useRouter();

  const handleProductClick = () => {
    const productData = encodeURIComponent(JSON.stringify(product));
    router.push(`/products/details?data=${productData}`);
  };

  return (
    <div
      onClick={handleProductClick}
      className="group relative bg-[var(--surface-panel)] p-4 rounded-2xl border border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] transition-all hover:cursor-pointer"
    >
      {/* Product Image */}
      <div className="w-full h-96 bg-[var(--surface-page)] rounded-lg overflow-hidden flex justify-center items-center"> {/* Increased height */}
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
    </div>
  );
}