import { notFound } from "next/navigation";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import { getSealedProductDetailServer } from "@/lib/pokemon/sealedProductDetailServer";
import SealedProductDetailClient from "@/components/pokemon/sealed-product-detail/SealedProductDetailClient";

async function load(params) {
  const { productId } = (await params) || {};
  return getSealedProductDetailServer(productId);
}

export async function generateMetadata({ params }) {
  try {
    const detail = await load(params);
    return buildRouteMetadata({
      path: buildSealedProductHref(detail.product.id),
      title: `${detail.product.name} — ${detail.set.name} RIP & Market Analysis | inDex`,
      description: detail.rip.available
        ? `${detail.product.name} from ${detail.set.name}: current sealed market price, price history, Product RIP, opening outcomes, and comparable sealed products.`
        : `${detail.product.name} from ${detail.set.name}: current sealed market price, price history, and comparable sealed products.`,
    });
  } catch { return {}; }
}

export default async function SealedProductCanonicalPage({ params }) {
  let detail;
  try { detail = await load(params); }
  catch (error) { if (error?.status === 404) notFound(); throw error; }
  return <SealedProductDetailClient initialDetail={detail} />;
}
