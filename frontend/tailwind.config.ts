import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      boxShadow: {
        panel: "0 16px 48px rgba(7, 63, 59, 0.08)",
      },
      colors: {
        "peacock-deep": "#073F3B",
        peacock: "#0C554C",
        emerald: "#0B7A5E",
        lime: "#B9E36A",
        warm: "#FCFCF8",
        "warm-green": "#F1F7F3",
        graphite: "#142521",
        slate: "#71817E",
        line: "#E2EBE7",
        ink: "#142521",
        mint: "#E4F2EA",
        lilac: "#EEF4F1",
        peach: "#F3F7E8",
      },
    },
  },
  plugins: [],
};

export default config;
