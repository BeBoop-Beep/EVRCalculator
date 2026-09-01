"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { useAuth } from "@/components/AuthContext";
import { createClient } from "@/lib/supabase/client";
import { buildAuthCallbackUrl, buildAuthCallbackUrlWithNext, currentReturnPath, sanitizeReturnPath } from "@/lib/auth/returnPath.mjs";
import { serializeOAuthReturnCookie } from "@/lib/auth/oauthState.mjs";

const initialState = { mode: "login", email: "", password: "", confirm: "", code: "", error: "", message: "", pending: false };
function reducer(state, action) {
  if (action.type === "mode") return { ...initialState, email: state.email, mode: action.mode };
  if (action.type === "field") return { ...state, [action.name]: action.value, error: "", message: "" };
  if (action.type === "pending") return { ...state, pending: action.value, error: action.value ? "" : state.error };
  if (action.type === "error") return { ...state, pending: false, error: action.value };
  if (action.type === "message") return { ...state, pending: false, message: action.value };
  return state;
}

function friendlyError(error, fallback) {
  const text = String(error?.message || "").toLowerCase();
  if (text.includes("rate") || text.includes("limit")) return "Too many attempts. Please wait and try again.";
  if (text.includes("expired") || text.includes("invalid")) return fallback;
  if (text.includes("provider") || text.includes("unsupported")) return "This sign-in provider is not available yet.";
  return fallback;
}

async function establishAppSession(session) {
  if (!session?.access_token) throw new Error("No verified authentication session was returned.");
  const response = await fetch("/api/auth/supabase/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accessToken: session.access_token }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.message || "Unable to prepare your account.");
}

function ProviderIcon({ provider }) {
  if (provider === "apple") return <span aria-hidden="true" className="text-xl leading-none">●</span>;
  return <span aria-hidden="true" className="font-bold text-[#4285f4]">G</span>;
}

export default function AuthPopover({ onClose, initialMode = "login", nextPath, embedded = false }) {
  const [state, dispatch] = useReducer(reducer, { ...initialState, mode: initialMode });
  const [cooldown, setCooldown] = useState(0);
  const panelRef = useRef(null);
  const { login, refreshUser } = useAuth();
  const googleEnabled = process.env.NEXT_PUBLIC_AUTH_GOOGLE_ENABLED !== "false";
  const appleEnabled = process.env.NEXT_PUBLIC_AUTH_APPLE_ENABLED !== "false";
  const destination = sanitizeReturnPath(nextPath || currentReturnPath());

  useEffect(() => {
    panelRef.current?.querySelector("input,button")?.focus();
  }, []);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const callbackUrl = () => buildAuthCallbackUrl(window.location.origin);
  const succeed = async () => {
    await refreshUser();
    onClose?.();
  };
  // OAuth is deliberately one continue flow. Supabase creates new provider users and
  // links a verified same-email provider identity to an existing Auth user when allowed.
  // The Supabase redirectTo is a stable, query-free `/auth/callback` URL (allow-list
  // friendly); the destination we actually want to return to travels via a short-lived
  // same-site cookie instead, consumed and cleared by the callback route.
  const continueWithProvider = async (provider) => {
    dispatch({ type: "pending", value: true });
    try {
      document.cookie = serializeOAuthReturnCookie(destination, { secure: window.location.protocol === "https:" });
      const { error } = await createClient().auth.signInWithOAuth({ provider, options: { redirectTo: callbackUrl() } });
      if (error) throw error;
    } catch (error) {
      dispatch({ type: "error", value: friendlyError(error, `Unable to continue with ${provider === "apple" ? "Apple" : "Google"}.`) });
    }
  };
  const passwordLogin = async () => {
    dispatch({ type: "pending", value: true });
    const result = await login(state.email.trim().toLowerCase(), state.password);
    if (result.error) dispatch({ type: "error", value: result.error });
    else {
      dispatch({ type: "pending", value: false });
      if (nextPath && typeof window !== "undefined") window.location.assign(destination);
      else onClose?.();
    }
  };
  const signup = async () => {
    if (state.password !== state.confirm) return dispatch({ type: "error", value: "Passwords do not match." });
    dispatch({ type: "pending", value: true });
    try {
      const { data, error } = await createClient().auth.signUp({
        email: state.email.trim().toLowerCase(), password: state.password,
        options: { emailRedirectTo: buildAuthCallbackUrlWithNext(window.location.origin, destination) },
      });
      if (error) throw error;
      if (!data.session) return dispatch({ type: "mode", mode: "confirmation-sent" });
      await establishAppSession(data.session);
      await succeed();
    } catch (error) { dispatch({ type: "error", value: friendlyError(error, "Unable to create the account. Check your details and try again.") }); }
  };
  const sendOtp = async () => {
    dispatch({ type: "pending", value: true });
    try {
      const { error } = await createClient().auth.signInWithOtp({
        email: state.email.trim().toLowerCase(),
        options: { shouldCreateUser: false },
      });
      if (error) throw error;
      setCooldown(60);
      dispatch({ type: "mode", mode: "email-code-verify" });
    } catch (error) { dispatch({ type: "error", value: friendlyError(error, "Unable to send a code. Please try again.") }); }
  };
  const verifyOtp = async () => {
    dispatch({ type: "pending", value: true });
    try {
      const { data, error } = await createClient().auth.verifyOtp({ email: state.email.trim().toLowerCase(), token: state.code.trim(), type: "email" });
      if (error) throw error;
      await establishAppSession(data.session);
      await succeed();
    } catch (error) { dispatch({ type: "error", value: friendlyError(error, "That code is invalid or expired.") }); }
  };
  const forgotPassword = async () => {
    dispatch({ type: "pending", value: true });
    try {
      const resetNext = `/login?mode=reset-password&next=${encodeURIComponent(destination)}`;
      const { error } = await createClient().auth.resetPasswordForEmail(state.email.trim().toLowerCase(), { redirectTo: buildAuthCallbackUrlWithNext(window.location.origin, resetNext) });
      if (error) throw error;
      dispatch({ type: "message", value: "If an account can receive recovery mail, a reset link is on its way." });
    } catch (error) { dispatch({ type: "error", value: friendlyError(error, "Unable to send a recovery email. Please try again.") }); }
  };
  const resetPassword = async () => {
    if (state.password !== state.confirm) return dispatch({ type: "error", value: "Passwords do not match." });
    dispatch({ type: "pending", value: true });
    try {
      const supabase = createClient();
      const { data, error } = await supabase.auth.updateUser({ password: state.password });
      if (error) throw error;
      const { data: sessionData } = await supabase.auth.getSession();
      await establishAppSession(sessionData.session);
      await succeed();
      window.history.replaceState({}, "", destination);
    } catch (error) { dispatch({ type: "error", value: friendlyError(error, "The recovery session expired. Request a new reset link.") }); }
  };

  const submit = (event) => {
    event.preventDefault();
    if (state.mode === "login") return passwordLogin();
    if (state.mode === "signup") return signup();
    if (state.mode === "email-code-request") return sendOtp();
    if (state.mode === "email-code-verify") return verifyOtp();
    if (state.mode === "forgot-password") return forgotPassword();
    if (state.mode === "reset-password") return resetPassword();
  };
  const title = state.mode === "signup" ? "Create your inDex account" : state.mode === "forgot-password" ? "Reset your password" : state.mode === "reset-password" ? "Choose a new password" : state.mode === "email-code-verify" ? "Enter your email code" : state.mode === "confirmation-sent" ? "Check your email" : "Welcome to inDex";
  const showProviders = ["login", "signup"].includes(state.mode);
  const showPassword = ["login", "signup", "reset-password"].includes(state.mode);
  const showEmail = ["login", "signup", "email-code-request", "email-code-verify", "forgot-password"].includes(state.mode);

  return (
    <section ref={panelRef} role="dialog" aria-modal={!embedded} aria-labelledby="auth-title" className={`${embedded ? "w-full" : "absolute right-0 top-full mt-2 w-[min(390px,calc(100vw-1rem))]"} set-dropdown-glass z-[1200] rounded-2xl p-5 shadow-2xl`}>
      <div className="flex items-start justify-between gap-4"><div><h2 id="auth-title" className="text-xl font-semibold text-[var(--text-primary)]">{title}</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">{state.mode === "confirmation-sent" ? "Use the confirmation link to finish creating your account." : "Sign in without leaving what you were exploring."}</p></div>{onClose && <button type="button" onClick={onClose} aria-label="Close authentication" className="rounded-md px-2 py-1 text-xl text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">×</button>}</div>
      {state.mode === "confirmation-sent" ? <button type="button" onClick={() => dispatch({ type: "mode", mode: "login" })} className="mt-5 w-full rounded-lg bg-brand px-4 py-2.5 font-semibold text-white">Back to login</button> : <>
        {showProviders && <><div className="mt-5 grid gap-2">{googleEnabled && <button type="button" disabled={state.pending} onClick={() => continueWithProvider("google")} className="flex items-center justify-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-white px-4 py-2.5 font-semibold text-slate-900 disabled:opacity-60"><ProviderIcon provider="google" />Continue with Google</button>}{appleEnabled && <button type="button" disabled={state.pending} onClick={() => continueWithProvider("apple")} className="flex items-center justify-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-black px-4 py-2.5 font-semibold text-white disabled:opacity-60"><ProviderIcon provider="apple" />Continue with Apple</button>}</div><div className="my-4 flex items-center gap-3 text-xs text-[var(--text-secondary)]"><span className="h-px flex-1 bg-[var(--border-subtle)]" />or<span className="h-px flex-1 bg-[var(--border-subtle)]" /></div></>}
        <form onSubmit={submit} className="grid gap-3">
          {showEmail && <label className="grid gap-1 text-sm font-medium">Email<input type="email" required autoComplete="email" value={state.email} disabled={state.mode === "email-code-verify"} onChange={(e) => dispatch({ type: "field", name: "email", value: e.target.value })} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2.5 outline-none focus:ring-2 focus:ring-[var(--accent)]" /></label>}
          {showPassword && <label className="grid gap-1 text-sm font-medium">Password<input type="password" required minLength={8} autoComplete={state.mode === "login" ? "current-password" : "new-password"} value={state.password} onChange={(e) => dispatch({ type: "field", name: "password", value: e.target.value })} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2.5 outline-none focus:ring-2 focus:ring-[var(--accent)]" /></label>}
          {(["signup", "reset-password"].includes(state.mode)) && <label className="grid gap-1 text-sm font-medium">Confirm password<input type="password" required minLength={8} autoComplete="new-password" value={state.confirm} onChange={(e) => dispatch({ type: "field", name: "confirm", value: e.target.value })} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2.5 outline-none focus:ring-2 focus:ring-[var(--accent)]" /></label>}
          {state.mode === "email-code-verify" && <label className="grid gap-1 text-sm font-medium">Code<input inputMode="numeric" autoComplete="one-time-code" required value={state.code} onChange={(e) => dispatch({ type: "field", name: "code", value: e.target.value.replace(/\D/g, "").slice(0, 8) })} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2.5 text-center text-lg tracking-[0.35em] outline-none focus:ring-2 focus:ring-[var(--accent)]" /></label>}
          {state.error && <p role="alert" className="text-sm text-red-400">{state.error}</p>}{state.message && <p role="status" className="text-sm text-emerald-400">{state.message}</p>}
          <button type="submit" disabled={state.pending} className="mt-1 rounded-lg bg-brand px-4 py-2.5 font-semibold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60">{state.pending ? "Please wait…" : state.mode === "signup" ? "Create account" : state.mode === "email-code-request" ? "Email me a code" : state.mode === "email-code-verify" ? "Verify code" : state.mode === "forgot-password" ? "Send reset link" : state.mode === "reset-password" ? "Update password" : "Log in"}</button>
        </form>
        <div className="mt-4 grid gap-2 text-center text-sm text-[var(--text-secondary)]">
          {state.mode === "login" && <><button type="button" onClick={() => dispatch({ type: "mode", mode: "forgot-password" })} className="hover:text-[var(--text-primary)]">Forgot password?</button><button type="button" onClick={() => dispatch({ type: "mode", mode: "email-code-request" })} className="hover:text-[var(--text-primary)]">Use an email code instead</button><button type="button" onClick={() => dispatch({ type: "mode", mode: "signup" })} className="hover:text-[var(--text-primary)]">New to inDex? Create account</button></>}
          {state.mode === "signup" && <button type="button" onClick={() => dispatch({ type: "mode", mode: "login" })}>Already have an account? Log in</button>}
          {state.mode === "email-code-verify" && <><button type="button" disabled={cooldown > 0} onClick={sendOtp}>{cooldown ? `Resend code in ${cooldown}s` : "Resend code"}</button><button type="button" onClick={() => dispatch({ type: "mode", mode: "email-code-request" })}>Change email</button></>}
          {["forgot-password", "email-code-request"].includes(state.mode) && <button type="button" onClick={() => dispatch({ type: "mode", mode: "login" })}>Back to login</button>}
        </div>
      </>}
    </section>
  );
}
