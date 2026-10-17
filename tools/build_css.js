// Build pipeline: Tailwind (purged) + site CSS + self-hosted font-faces -> one minified file.
//   npm run build:css   ->  static/css/app.min.css
const { execFileSync } = require("child_process");
const fs = require("fs");
const esbuild = require("esbuild");

execFileSync("npx", ["tailwindcss", "-c", "tailwind.config.js", "-i", "assets/tailwind.input.css", "-o", "assets/tailwind.out.css", "--minify"], { stdio: "inherit" });
const parts = ["assets/fonts.css", "assets/tailwind.out.css", "assets/styles.src.css"].map(f => fs.readFileSync(f, "utf8"));
const out = esbuild.transformSync(parts.join("\n"), { loader: "css", minify: true, legalComments: "none" }).code;
fs.mkdirSync("static/css", { recursive: true });
fs.writeFileSync("static/css/app.min.css", out);
console.log(`app.min.css ${(out.length / 1024).toFixed(1)} KB (sources: ${parts.map(p => (p.length / 1024).toFixed(0) + "KB").join(" + ")})`);
