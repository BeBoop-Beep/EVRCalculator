This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://github.com/vercel/next.js/tree/canary/packages/create-next-app).

## Authentication configuration

Inline authentication uses Supabase Auth with PKCE, then exchanges the verified Supabase session for the existing inDex application session.

```env
NEXT_PUBLIC_SUPABASE_URL=https://zwxzxuuawalvwioadhmf.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_replace_me
NEXT_PUBLIC_AUTH_GOOGLE_ENABLED=false
NEXT_PUBLIC_AUTH_APPLE_ENABLED=false
```

Set provider flags to `true` only after enabling each provider in the Supabase Dashboard. Provider secrets remain in Supabase/provider configuration and must never use a `NEXT_PUBLIC_` variable. The backend still requires `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `JWT_SECRET` for verified profile provisioning and inDex JWT issuance.

Google OAuth is intentionally one **Continue with Google** flow for both login and signup. A new verified Google identity can create an account, an existing Google identity signs in, and Supabase may automatically link a verified same-email Google identity to an existing Auth user. Do not fork Google into separate login-only and signup-only client flows.

### Supabase Auth URL configuration

The application's OAuth `redirectTo` is always the **stable, query-free** path `/auth/callback` on the origin that initiated PKCE (`window.location.origin`) — never `/auth/callback?next=...`. The post-auth destination is *not* part of that URL; it travels separately in a short-lived, same-site `pkce_return_path` cookie (`lib/auth/oauthState.mjs`) that the callback route reads once and clears. This is deliberate: Supabase's redirect allow-list must match the callback URL, and a query string is part of that match for any origin other than the configured Site URL, so a stable, argument-free callback URL is what actually stays allow-list friendly.

Configure Supabase **Authentication → URL Configuration** with:

- Site URL: `https://inthedex.io` (the apex domain currently serving production traffic)
- Redirect URL: `https://inthedex.io/auth/callback`
- If `www` can initiate authentication: also add `https://www.inthedex.io/auth/callback`
- Local development: `http://localhost:3000/auth/callback`
- Vercel previews: not enabled by default — see below if you turn them on

This app has a separate, pre-existing SEO canonical-domain policy (`lib/seo/siteUrl.mjs`, currently `https://www.inthedex.io`) for `og:url`/sitemap purposes. That policy governs crawler-facing metadata only and has no bearing on the auth redirect URLs above; do not try to make the two agree by editing either one, and do not add a second "canonical production domain" constant to the auth code. If the apex-vs-`www` split itself needs to be resolved, that is a separate decision — see Follow-ups below.

Because the PKCE verifier and the resulting host-scoped application session must not move to a different hostname mid-flow, the app always builds `/auth/callback` on the *same* origin that started the request. Prefer redirecting `www` traffic to the apex before login begins; if both hosts can genuinely initiate auth, add both exact callback URLs to Supabase's allow-list as shown above.

The exact callback URL must be present in Supabase's redirect allow-list. If `redirectTo` is not allowed, Supabase falls back to the configured Site URL instead of erroring — so a stale Site URL (e.g. still `http://localhost:3000`) can silently send a production OAuth completion back to localhost.

**Server-generated email links** (signup confirmation, password recovery) are opened directly from an email client, possibly on a different device, so there's no prior request on which to set a cookie. Those links keep the return path in the callback URL's query string (`buildAuthCallbackUrlWithNext`) and are built from a trusted, configured origin (`NEXT_PUBLIC_BASE_URL` via `lib/runtimeUrls.js`) — never from the raw request `Host` header, which a client can spoof. If Vercel previews need email-link support, set `NEXT_PUBLIC_BASE_URL` to the preview's own origin in that deployment's environment and add its exact `/auth/callback` URL to Supabase's redirect allow-list; there is no wildcard/any-host fallback.

### Follow-ups (not part of this change)

- **Apex vs. `www`**: production traffic and `SEO`/backend config disagree on the canonical host (`lib/seo/siteUrl.mjs` defaults to `www`, `backend/.env.example` and the auth redirect URL above use the apex). Resolving that is a separate decision, not an auth fix.
- **Email confirmation across devices**: signup/password-recovery links currently rely on PKCE, which requires completing the flow in the same browser that started it. Supabase's token-hash confirmation endpoints are more robust for cross-device email confirmation; adopting them would be a deliberate, scoped follow-up, not something bundled into Google-auth hardening.

## inDex Mobile UI Invariants

1. Mobile is a dedicated composition, not desktop stacked vertically.
2. Large desktop context/container cards normally disappear on mobile; major sections use the established thin divider treatment instead.
3. Mobile cards represent discrete data, entities, or actions—not containers whose only purpose is holding other cards.
4. Preserve usable horizontal width with one consistent page gutter.
5. Secondary explanatory copy collapses before primary metrics, ranks, or tiers do.
6. Analytical summaries should communicate in roughly one viewport where practical.
7. Interactive targets are at least 44px high and preferably 48px.
8. QA mobile UI at 375px, 390px, and 430px, plus the 768px transition.
9. A mobile UI pass is not complete until screenshots have been visually reviewed.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.js`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out the [Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is with the [Vercel Platform](https://vercel.com/new?utm_source=create-next-app&utm_medium=default-template&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
"# index " 
