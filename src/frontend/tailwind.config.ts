import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Severity colors matching api-design.md §2.2.5
        severity: {
          critical: "#ef4444",  // red-500
          warning: "#f97316",   // orange-500
          info: "#eab308",      // yellow-500
        },
      },
    },
  },
  plugins: [],
};

export default config;
