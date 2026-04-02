import { redirect } from "next/navigation";

export default async function LegacyProductDetailsPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const rawData = resolvedSearchParams?.data;

  if (typeof rawData === "string" && rawData.length > 0) {
    try {
      const decoded = JSON.parse(decodeURIComponent(rawData));
      const productId = decoded?._id || decoded?.id;
      if (productId) {
        redirect(`/sealed-products/${encodeURIComponent(String(productId))}`);
      }
    } catch {
      // Fall through to default redirect.
    }
  }

  redirect("/products");
}