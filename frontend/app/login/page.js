import AuthPopover from "@/components/AuthPopover";
import { sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";

export default async function LoginPage({ searchParams }) {
  const params = await searchParams;
  const requestedMode = params?.mode;
  const mode = ["login", "signup", "forgot-password", "reset-password", "email-code-request"].includes(requestedMode) ? requestedMode : "login";
  return (
    <main className="mx-auto w-full max-w-lg px-4 py-12 sm:px-6">
      {params?.authError ? <p role="alert" className="mb-4 rounded-lg border border-red-400/30 bg-red-950/20 p-3 text-sm text-red-300">{String(params.authError).slice(0, 240)}</p> : null}
      <AuthPopover embedded initialMode={mode} nextPath={sanitizeReturnPath(params?.next)} />
    </main>
  );
}
