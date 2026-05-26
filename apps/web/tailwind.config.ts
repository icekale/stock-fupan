import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        panel: "#f8fafc",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.06), 0 12px 32px rgba(15, 23, 42, 0.05)",
      },
    },
  },
  plugins: [],
};

export default config;
