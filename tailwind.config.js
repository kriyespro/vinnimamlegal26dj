/** Build: npm run build:css  (output is committed so servers don't need Node) */
const colors = require("tailwindcss/colors");
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        // Brand palette: blue + orange + white
        navy: { DEFAULT: "#0B1F4D", light: "#12307A", dark: "#071536" },
        royal: { DEFAULT: "#1D4ED8", light: "#3B82F6", dark: "#1E40AF" },
        gold: { DEFAULT: "#F97316", light: "#FB923C", dark: "#EA580C" }, // legacy name = brand orange
        brand: { orange: "#F97316", blue: "#1D4ED8", tint: "#F5F8FF" },
        // Decorative scales collapse into the brand hues (semantic green/red stay as is)
        purple: colors.blue, violet: colors.blue, indigo: colors.blue, sky: colors.blue,
        pink: colors.orange, rose: colors.orange, amber: colors.orange, fuchsia: colors.orange,
        slate: { 50: "#F5F8FF", 100: "#EAF0FB" },
      },
      fontFamily: { inter: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
