// node tools/site_check.js — crawls public pages + (optionally) logged-in pages; reports failed requests,
// console errors, broken images, dead internal links, missing alt text and duplicate ids.
const puppeteer = require("puppeteer-core");
const BASE = "http://localhost:8000";
const PUBLIC = ["/", "/about", "/services", "/services-by-state", "/services-by-state/gujarat", "/pricing", "/business-registration", "/partnership", "/msme", "/trademark", "/contracts", "/marriage-certificate", "/adoption", "/expert-portal", "/deadlines", "/legal-glossary", "/faq", "/blog", "/contact", "/portal-usage-policy", "/portal", "/search?q=trademark"];
const PW = process.env.DEMO_PW;
const LOGGED = { client: ["/portal/dashboard", "/billing/invoices/2"], partner: ["/portal/dashboard"], staff: ["/portal/dashboard"], ceo: ["/portal/dashboard", "/admin/", "/admin/users/", "/admin/users/new/", "/admin/cases/", "/admin/cases/new/", "/admin/leads/", "/admin/billing/", "/admin/audit/"] };
const seen = new Set();
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const problems = [];
  async function visit(page, url) {
    const errs = [];
    const onResp = r => { if (r.status() >= 400 && !r.url().includes("favicon")) errs.push(`HTTP ${r.status()} ${r.url().replace(BASE, "")}`); };
    const onConsole = m => { if (m.type() === "error") errs.push("console: " + m.text().slice(0, 160)); };
    const onPageErr = e => errs.push("pageerror: " + String(e).slice(0, 160));
    page.on("response", onResp); page.on("console", onConsole); page.on("pageerror", onPageErr);
    await page.goto(BASE + url, { waitUntil: "networkidle2", timeout: 30000 }).catch(e => errs.push("nav: " + e.message));
    const info = await page.evaluate(() => {
      const broken = [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.getAttribute("src"));
      const noAlt = [...document.images].filter(i => !i.hasAttribute("alt")).length;
      const ids = {}; document.querySelectorAll("[id]").forEach(e => ids[e.id] = (ids[e.id] || 0) + 1);
      const dupes = Object.keys(ids).filter(k => ids[k] > 1);
      const links = [...new Set([...document.querySelectorAll("a[href]")].map(a => a.getAttribute("href")).filter(h => h.startsWith("/") && !h.startsWith("//")))];
      const emptyLinks = [...document.querySelectorAll("a[href='#']")].length;
      const unlabeled = [...document.querySelectorAll("input:not([type=hidden]):not([type=submit]):not([type=checkbox]), select, textarea")].filter(e => !e.getAttribute("aria-label") && !e.id && !e.closest("label") && !(e.previousElementSibling && e.previousElementSibling.tagName === "LABEL") && !e.getAttribute("placeholder")).length;
      const h1 = document.querySelectorAll("h1").length;
      return { broken, noAlt, dupes, links, emptyLinks, unlabeled, h1, title: document.title };
    });
    page.off("response", onResp); page.off("console", onConsole); page.off("pageerror", onPageErr);
    return { errs: [...new Set(errs)], ...info };
  }
  const pages = [];
  const page = await browser.newPage();
  for (const u of PUBLIC) { const r = await visit(page, u); pages.push([u, r]); }
  if (PW) for (const role of Object.keys(LOGGED)) {
    const ctx = await browser.createBrowserContext(); const p = await ctx.newPage();
    await p.goto(BASE + "/portal", { waitUntil: "networkidle2" });
    await p.evaluate((role, pw) => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")); f.querySelector("input[name=email]").value = role + "@demo.local"; f.querySelector("input[name=password]").value = pw; (f.querySelector("input[name=role]") || {}).value = role; f.querySelector("input[name=policy]").checked = true; f.submit(); }, role, PW);
    await p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {});
    for (const u of LOGGED[role]) { const r = await visit(p, u); pages.push([`${role}:${u}`, r]); }
    await ctx.close();
  }
  // dead internal links
  const allLinks = new Set(); pages.forEach(([, r]) => r.links.forEach(l => allLinks.add(l.split("#")[0].split("?")[0])));
  const dead = [];
  for (const l of allLinks) { if (!l || l.startsWith("/static") || l.startsWith("/portal/logout")) continue; const res = await page.goto(BASE + l, { waitUntil: "domcontentloaded" }).catch(() => null); const st = res ? res.status() : 0; if (st >= 400 && st !== 405) dead.push(`${st} ${l}`); }
  for (const [u, r] of pages) {
    const flags = [];
    if (r.errs.length) flags.push("ERR " + r.errs.join(" | "));
    if (r.broken.length) flags.push("BROKEN-IMG " + r.broken.join(","));
    if (r.noAlt) flags.push(`${r.noAlt} img w/o alt`);
    if (r.dupes.length) flags.push("DUP-IDS " + r.dupes.join(","));
    if (r.emptyLinks) flags.push(`${r.emptyLinks} href="#"`);
    if (r.h1 !== 1) flags.push(`h1 count ${r.h1}`);
    if (r.unlabeled) flags.push(`${r.unlabeled} unlabeled fields`);
    console.log((flags.length ? "!! " : "ok ") + u.padEnd(34) + flags.join("  "));
  }
  console.log("dead internal links:", dead.length ? dead.join(", ") : "none");
  await browser.close();
})();
