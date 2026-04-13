"use client"; // Add this directive for client-side interactivity
import { useRouter } from "next/navigation"; // Import useRouter
import styles from "./NewMerchandise.module.css";
import Image from "next/image";

export default function NewMerchandise({ merchandise }) {
  const router = useRouter(); // Initialize the router

  const sortedMerchandise = Array.isArray(merchandise)
    ? [...merchandise]
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
        .slice(0, 2) // Get the first TWO merchandise
    : [];


  // Function to handle merch click
  const handleMerchandiseClick = (merch) => {
    // Convert the merch object to a URL-friendly string
    const merchData = encodeURIComponent(JSON.stringify(merch));
    // Navigate to the merch details page with the merch data
    router.push(`/merchandise/details?data=${merchData}`);
  };

  return (
    <div className="py-2">
    <div className={styles.container}>
     

      {/* Grid Layout for Images */}
      <div className={styles.merchandiseGrid}>
        {sortedMerchandise.length > 0 ? (
          sortedMerchandise.map((merch, index) => (
            <div
              key={index}
              className={styles.imageBlock}
              onClick={() => handleMerchandiseClick(merch)} // Handle merch click
            >
              <Image
                unoptimized
                src={merch.images?.[0] || "/fallback-image.jpg"} // Fallback image if missing
                alt={merch.title}
                width={1200}
                height={1200}
                className={styles.merchImage}
              />
              <div className={styles.overlay}>
                <h3 className={styles.merchTitle}>{merch.title}</h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation(); // Prevent event bubbling
                    handleMerchandiseClick(merch); // Navigate to merch details
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
    </div>
  );
}