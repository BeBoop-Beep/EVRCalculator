import { redirect } from "next/navigation";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";

export default async function LegacyProductDetailsPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const rawData = resolvedSearchParams?.data;

  if (typeof rawData === "string" && rawData.length > 0) {
    try {
      const decoded = JSON.parse(decodeURIComponent(rawData));
      const productId = decoded?._id || decoded?.id;
      const href = buildSealedProductHref(productId);
      if (href) {
        redirect(href);
      }
    } catch {
      // Fall through to default redirect.
    }
  }

  redirect("/products");
}
