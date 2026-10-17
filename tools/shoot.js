// node tools/shoot.js <width> <outDir> <login-email|role|-> <path> [segments]
// Needs DEMO_PW env for logins. Uses local Chrome via puppeteer-core.
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const [width, out, who, path, segs] = [parseInt(process.argv[2]), process.argv[3], process.argv[4], process.argv[5], parseInt(process.argv[6] || "3")];
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const p = await browser.newPage();
  await p.setViewport({ width, height: parseInt(process.env.VH || "844"), isMobile: width < 600, hasTouch: width < 600 });
  if (who !== "-") {
    const email = who.includes("@") ? who : who + "@demo.local";
    await p.goto("http://localhost:8000/portal", { waitUntil: "networkidle2" });
    await p.evaluate((email, pw) => {
      const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]"));
      f.querySelector("input[name=email]").value = email;
      f.querySelector("input[name=password]").value = pw;
      (f.querySelector("input[name=role]") || {}).value = email.split("@")[0].replace(/2$/, "");
      f.querySelector("input[name=policy]").checked = true;
      f.submit();
    }, email, process.env.DEMO_PW);
    await p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {});
  }
  await p.goto("http://localhost:8000" + path, { waitUntil: "networkidle2" });
  await new Promise(r => setTimeout(r, 500));
  const h = await p.evaluate(() => document.documentElement.scrollHeight);
  const sw = await p.evaluate(() => document.documentElement.scrollWidth);
  const name = (who === "-" ? "" : who.split("@")[0]) + path.replace(/[^a-z0-9]+/gi, "_");
  for (let i = 0; i < segs && i * parseInt(process.env.VH || "844") < h; i++) {
    await p.evaluate(y => window.scrollTo(0, y), i * parseInt(process.env.VH || "844"));
    await new Promise(r => setTimeout(r, 250));
    await p.screenshot({ path: `${out}/${name}_${i}.png` });
  }
  console.log(name, "height", h, "scrollWidth", sw);
  await browser.close();
})();
