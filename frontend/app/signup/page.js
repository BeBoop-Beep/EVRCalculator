import AuthPopover from "@/components/AuthPopover";
import { sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";

export default async function SignupPage({ searchParams }) {
  const params = await searchParams;
  return <main className="mx-auto w-full max-w-lg px-4 py-12 sm:px-6"><AuthPopover embedded initialMode="signup" nextPath={sanitizeReturnPath(params?.next)} /></main>;
}
