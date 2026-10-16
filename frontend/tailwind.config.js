/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        finpay: {
          light: "#60a5fa",
          DEFAULT: "#2563eb",
          dark: "#1e40af",
        },
        vaultly: {
          light: "#fb923c",
          DEFAULT: "#f97316",
          dark: "#c2410c",
        },
      },
    },
  },
  plugins: [],
};
