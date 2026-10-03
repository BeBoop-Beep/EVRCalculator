import TreatmentPreferenceStudyClient from "./TreatmentPreferenceStudyClient";

export const metadata = {
  title: "Card Presentation Preference Study | inDex",
  description: "A blinded research study about Pokémon card artwork and presentation preferences.",
  robots: {
    index: false,
    follow: false,
  },
};

export default function TreatmentPreferenceStudyPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:py-14">
      <header className="mx-auto mb-8 max-w-3xl text-center">
        <p className="text-sm font-semibold uppercase tracking-[.18em] text-[var(--accent)]">
          inDex Research
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-[var(--text-primary)] sm:text-4xl">
          Card presentation preference study
        </h1>
        <p className="mt-4 text-base leading-7 text-[var(--text-secondary)]">
          You will see 12 pairs of cards. For each pair, choose the version you would rather own for the artwork and presentation itself, or choose no preference if they are effectively tied.
        </p>
        <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
          We do not ask for your name or account information. The study uses a random browser-local session identifier only to prevent accidental duplicate responses and to resume an unfinished block.
        </p>
      </header>

      <TreatmentPreferenceStudyClient />
    </main>
  );
}
