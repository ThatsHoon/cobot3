import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "var(--base)",
        panel: "var(--panel)",
        line: "var(--line)",
        phos: "var(--phos)",      // 인광 그린 (정상/주신호)
        amber: "var(--amber)",    // 경보/주의
        alert: "var(--alert)",    // 위협/사격
        ink: "var(--ink)",
        dim: "var(--dim)",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        glow: "0 0 12px -2px var(--phos)",
        alertglow: "0 0 16px -2px var(--alert)",
      },
    },
  },
  plugins: [],
};
export default config;
