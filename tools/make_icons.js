// Generates static/img/{icon-192,icon-512,apple-touch-icon,og-default}.png from the brand mark (uses local Chrome).
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const svg = fs.readFileSync("static/favicon.svg", "utf8");
(async () => {
  fs.mkdirSync("static/img", { recursive: true });
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const p = await browser.newPage();
  for (const [name, size, pad] of [["icon-192", 192, 0], ["icon-512", 512, 0], ["apple-touch-icon", 180, 0]]) {
    await p.setViewport({ width: size, height: size, deviceScaleFactor: 1 });
    await p.setContent(`<body style="margin:0;background:transparent"><div style="width:${size}px;height:${size}px">${svg.replace("<svg ", `<svg width="${size}" height="${size}" `)}</div></body>`);
    await p.screenshot({ path: `static/img/${name}.png`, omitBackground: true });
  }
  await p.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
  await p.setContent(`<body style="margin:0;font-family:Inter,Helvetica,Arial,sans-serif">
    <div style="width:1200px;height:630px;position:relative;overflow:hidden;color:#fff;background:radial-gradient(900px 500px at 92% -10%,rgba(249,115,22,.45),transparent 62%),radial-gradient(800px 520px at -5% 110%,rgba(96,165,250,.45),transparent 60%),linear-gradient(135deg,#1E40AF,#1D4ED8 55%,#2563EB)">
      <div style="position:absolute;left:72px;top:64px;display:flex;align-items:center;gap:20px"><div style="width:84px;height:84px">${svg.replace("<svg ", '<svg width="84" height="84" ')}</div><div style="font-size:54px;font-weight:800;letter-spacing:-1px">Vinnita<span style="color:#FDBA74">Legal</span></div></div>
      <div style="position:absolute;left:72px;top:230px;width:900px;font-size:76px;line-height:1.05;font-weight:800;letter-spacing:-2px">Legal work made simple —<br><span style="color:#FDBA74">registered, protected, compliant.</span></div>
      <div style="position:absolute;left:72px;bottom:64px;font-size:30px;color:rgba(255,255,255,.88)">Business registration · Trademark · Contracts · MSME — Gujarat</div>
      <div style="position:absolute;right:72px;bottom:60px;background:#fff;color:#1D4ED8;font-weight:800;font-size:28px;padding:16px 30px;border-radius:999px">Free consultation →</div>
    </div></body>`);
  await p.screenshot({ path: "static/img/og-default.jpg", type: "jpeg", quality: 84 });
  await browser.close();
  for (const f of fs.readdirSync("static/img")) console.log(f, fs.statSync("static/img/" + f).size, "bytes");
})();
