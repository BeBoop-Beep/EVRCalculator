This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://github.com/vercel/next.js/tree/canary/packages/create-next-app).

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

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
"# index " 
