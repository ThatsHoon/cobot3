import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "var(--base)",
        panel: "var(--panel)",
        "panel-2": "var(--panel-2)",
        line: "var(--line)",
        "line-2": "var(--line-2)",
        phos: "var(--phos)",
        "phos-dim": "var(--phos-dim)",
        amber: "var(--amber)",
        "amber-dim": "var(--amber-dim)",
        alert: "var(--alert)",
        "alert-dim": "var(--alert-dim)",
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        dim: "var(--dim)",
        graphite: "var(--graphite)",
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
