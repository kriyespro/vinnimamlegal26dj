// Usage: node tools/mobile_audit.js [width] [outDir]  — screenshots + horizontal-overflow report (uses local Chrome)
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const width = parseInt(process.argv[2] || "390", 10);
const out = process.argv[3] || "/tmp/shots";
const BASE = "http://localhost:8000";
const PUBLIC = ["/", "/services", "/pricing", "/contact", "/about", "/faq", "/blog", "/trademark", "/business-registration", "/msme", "/partnership", "/contracts", "/marriage-certificate", "/adoption", "/expert-portal", "/deadlines", "/legal-glossary", "/services-by-state/gujarat", "/portal-usage-policy", "/portal"];
const ROLES = { client: ["/portal/dashboard"], partner: ["/portal/dashboard"], staff: ["/portal/dashboard"], ceo: ["/portal/dashboard"] };
const PW = process.env.DEMO_PW;
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const report = [];
  async function check(page, url, name) {
    await page.goto(BASE + url, { waitUntil: "networkidle2", timeout: 30000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 400));
    const info = await page.evaluate((w) => {
      const de = document.documentElement;
      const over = [];
      if (de.scrollWidth > w + 1) {
        document.querySelectorAll("body *").forEach(el => {
          const r = el.getBoundingClientRect();
          if (r.right > w + 1 && r.width > 0 && getComputedStyle(el).position !== "fixed") {
            let p = el.parentElement, clipped = false;
            while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { clipped = true; break; } p = p.parentElement; }
            if (!clipped) over.push(el.tagName.toLowerCase() + "." + (el.className || "").toString().split(" ").slice(0, 3).join(".") + " r=" + Math.round(r.right));
          }
        });
      }
      const small = [...document.querySelectorAll("a,button,input,select")].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 30 && getComputedStyle(e).display !== "none"; }).length;
      return { sw: de.scrollWidth, over: over.slice(0, 6), small, title: document.title };
    }, width);
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: false });
    report.push({ url: name, ...info });
  }
  const page = await browser.newPage();
  await page.setViewport({ width, height: 800, deviceScaleFactor: 1, isMobile: width < 600, hasTouch: width < 600 });
  for (const u of PUBLIC) await check(page, u, "pub" + (u === "/" ? "_home" : u.replace(/\//g, "_")));
  if (PW) {
    for (const role of Object.keys(ROLES)) {
      const ctx = await browser.createBrowserContext();
      const p = await ctx.newPage();
      await p.setViewport({ width, height: 800, isMobile: width < 600, hasTouch: width < 600 });
      await p.goto(BASE + "/portal", { waitUntil: "networkidle2" });
      await p.evaluate((role, pw) => {
        const f = [...document.querySelectorAll("form")].find(f => f.querySelector('input[name=action][value=login]'));
        f.querySelector("input[name=email]").value = role + "@demo.local";
        f.querySelector("input[name=password]").value = pw;
        (f.querySelector("input[name=role]") || {}).value = role;
        f.querySelector("input[name=policy]").checked = true;
        f.submit();
      }, role, PW);
      await p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {});
      for (const u of ROLES[role]) await check(p, u, `${role}_dash`);
      await ctx.close();
    }
  }
  await browser.close();
  for (const r of report) console.log(`${r.sw > width + 1 ? "OVERFLOW" : "ok      "} ${String(r.sw).padStart(4)} small=${String(r.small).padStart(3)} ${r.url}${r.over.length ? "\n      " + r.over.join("\n      ") : ""}`);
})();
