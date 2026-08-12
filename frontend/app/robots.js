import { buildRobotsPolicy } from "@/lib/seo/robotsPolicy.mjs";

/**
 * Framework-native robots route — Next App Router serves this at /robots.txt.
 *
 * The policy itself lives in lib/seo/robotsPolicy.mjs so it can be unit tested
 * without the "@/" bundler alias. This file is only the route binding.
 */
export default function robots() {
  return buildRobotsPolicy();
}
