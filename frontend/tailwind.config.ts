import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      boxShadow: {
        panel: "0 4px 24px rgba(19, 47, 64, 0.045)",
      },
      colors: {
        "peacock-deep": "#132F40",
        peacock: "#11646D",
        emerald: "#147C86",
        lime: "#A8DED4",
        warm: "#EEF3F6",
        "warm-green": "#E7F1F3",
        graphite: "#172936",
        slate: "#64747D",
        line: "#D7E2E5",
        ink: "#172936",
        mint: "#D8F0ED",
        lilac: "#EDF3F7",
        peach: "#F6F2E9",
      },
    },
  },
  plugins: [],
};

export default config;
