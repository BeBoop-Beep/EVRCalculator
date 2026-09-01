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

Production uses the apex domain as the canonical application origin. Configure Supabase **Authentication → URL Configuration** with:

- Site URL: `https://inthedex.io`
- Redirect URL: `https://inthedex.io/auth/callback`
- Optional `www` alias: `https://www.inthedex.io/auth/callback`
- Local development: `http://localhost:3000/auth/callback`

The application canonicalizes both production hostnames to `https://inthedex.io/auth/callback` while preserving localhost and other development origins. The exact callback URL still must be present in Supabase's redirect allow-list. If `redirectTo` is not allowed, Supabase can fall back to the configured Site URL; a stale Site URL such as `http://localhost:3000` will therefore send a production OAuth completion to localhost instead of `/auth/callback`.

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

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out the [Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is with the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=chatgpt.com).

See the [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
"# index " 
