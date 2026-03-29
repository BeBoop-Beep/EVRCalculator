"use client"; // Add this directive for client-side interactivity
import { useRouter } from "next/navigation"; // Import useRouter
import styles from "./NewRipAndShip.module.css";
import Image from "next/image";

export default function NewProducts({ products }) {
  const router = useRouter(); // Initialize the router

  const sortedProducts = Array.isArray(products)
    ? [...products]
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
        .slice(0, 1) 
    : [];

  // Function to handle product click
  const handleProductClick = (product) => {
    // Convert the product object to a URL-friendly string
    const productData = encodeURIComponent(JSON.stringify(product));
    // Navigate to the product details page with the product data
    router.push(`/products/details?data=${productData}`);
  };

  return (
    <div className={styles.container}>
      <a href="/products" className={styles.titleContainer}>
        <h2 className={`${styles.titleTwo} ${styles.fadeIn}`}>Let&apos;s Rip Into Some Packs Together</h2>
        <h1 className={`${styles.title} ${styles.slideUp}`}>2/28/2025</h1>
        <h2 className={`${styles.titleTwo} ${styles.fadeIn}`}>
          Don&apos;t Miss Our Next Exciting Stream!
        </h2>
      </a>

      <div className={styles.productsGrid}>
        {sortedProducts.length > 0 ? (
          sortedProducts.map((product, index) => (
            <div
              key={index}
              className={styles.imageBlock}
              onClick={() => handleProductClick(product)} // Handle product click
            >
              <Image
                unoptimized
                src={product.images?.[0] || "/fallback-image.jpg"} // Fallback image if missing
                alt={product.title}
                width={1200}
                height={1200}
                className={styles.productImage}
              />
              <div className={styles.overlay}>
                <h3 className={styles.productTitle}>{product.title}</h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation(); // Prevent event bubbling
                    handleProductClick(product); // Navigate to product details
                  }}
                  className={styles.shopButton}
                >
                  Shop
                </button>
              </div>
            </div>
          ))
        ) : (
          <p>No image available</p>
        )}
      </div>
    </div>
  );
}