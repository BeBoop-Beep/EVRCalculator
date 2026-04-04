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
        primary: "rgb(2 6 23)", // Dark slate base
        brand: "#059669", // Emerald green - default
        "brand-dark": "#047857", // Emerald - hover
        "brand-active": "#065F46", // Emerald - active
        accent: "#FACC15", // Electric yellow - highlights & insights
        "accent-dark": "#EAB308", // Dark yellow
        "accent-light": "#FDE68A", // Light yellow
        success: "#059669", // Chart: upward trends
        danger: "#EF4444", // Chart: downward trends
        warning: "#F59E0B", // Chart: warnings
        neutral: "#94A3B8", // Chart: stable data
        "neutral-dark": "#374151", // Dark Gray for text
        "neutral-light": "#F8FAFC", // Light Gray background
        background: "var(--background)", // CSS variable for background
        foreground: "var(--foreground)", // CSS variable for foreground
      },
      transitionDuration: {
        100: "100ms",
        200: "200ms",
        300: "300ms",
      },
      animation: {
        fadeIn: "fadeIn 0.8s ease-out forwards",
        slideUp: "slideUp 1s ease-out forwards",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
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
