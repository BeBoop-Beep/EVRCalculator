/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  important: true,
  theme: {
    extend: {
      colors: {
        primary: "rgb(2 6 23)", // Dark Blue
        accent: "#FACC15", // Gold
        "accent-dark": "#FFEB3B", // Dark yellow
        "accent-light": "#FFF176", // Lighter Gold
        "neutral-dark": "#374151", // Dark Gray for text
        "neutral-light": "#F8FAFC", // Light Gray background
        background: "var(--background)", // CSS variable for background
        foreground: "var(--foreground)", // CSS variable for foreground
      },
      animation: {
        fadeIn: "fadeIn 0.8s ease-out forwards",
        slideUp: "slideUp 1s ease-out forwards",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
