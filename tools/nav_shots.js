// node tools/nav_shots.js <outDir>  — desktop nav, both dropdowns, search, and mobile menu screenshots
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const out = process.argv[2] || "/tmp/nav";
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  for (const [w, label] of [[1600, "wide"], [1280, "desktop"], [1024, "lg"]]) {
    const p = await browser.newPage();
    await p.setViewport({ width: w, height: 700 });
    await p.goto("http://localhost:8000/", { waitUntil: "networkidle2" });
    await p.screenshot({ path: `${out}/${label}_nav.png`, clip: { x: 0, y: 0, width: w, height: 90 } });
    const btns = await p.$$("nav .group > button");
    for (let i = 0; i < btns.length; i++) {
      await btns[i].hover();
      await wait(400);
      await p.screenshot({ path: `${out}/${label}_dd${i}.png`, clip: { x: 0, y: 0, width: w, height: 650 } });
    }
    await p.mouse.move(5, 400);
    let search = null; for (const h of await p.$$('nav input[type=search]')) { if (await h.boundingBox()) { search = h; break; } }
    if (search && label === "wide") { await search.click(); await wait(300); await p.screenshot({ path: `${out}/${label}_search.png`, clip: { x: 0, y: 0, width: w, height: 500 } }); }
    const info = await p.evaluate(() => {
      const nav = document.querySelector("nav");
      const row = nav.querySelector(".hidden.lg\\:flex");
      return { navH: nav.getBoundingClientRect().height, sw: document.documentElement.scrollWidth, wrapped: row && row.getBoundingClientRect().height };
    });
    console.log(label, JSON.stringify(info));
    await p.close();
  }
  const m = await browser.newPage();
  await m.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await m.goto("http://localhost:8000/", { waitUntil: "networkidle2" });
  await m.tap("nav button.lg\\:hidden");
  await wait(500);
  await m.screenshot({ path: `${out}/mobile_menu.png` });
  await browser.close();
})();
