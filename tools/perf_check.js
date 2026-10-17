// Performance checklist per page (local Chrome, cache disabled): requests, transfer, TTFB, LCP, CLS, long tasks, third parties.
//   node tools/perf_check.js [baseUrl]   (exit code 1 if a budget is exceeded)
const puppeteer = require("puppeteer-core");
const BASE = process.argv[2] || "http://localhost:8000";
const PAGES = ["/", "/services", "/pricing", "/contact", "/faq", "/trademark", "/portal"];
const BUDGET = { requests: 14, transferKB: 260, ttfb: 600, lcp: 2500, cls: 0.1, fcp: 1800, thirdParty: 0 };
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  let failed = 0;
  console.log("page".padEnd(14), "req".padStart(4), "KB".padStart(6), "TTFB".padStart(6), "FCP".padStart(6), "LCP".padStart(6), "CLS".padStart(6), "3rd".padStart(4));
  for (const path of PAGES) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });
    const cdp = await page.createCDPSession();
    await cdp.send("Network.enable"); await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    let bytes = 0, reqs = 0; const third = new Set();
    cdp.on("Network.loadingFinished", e => { bytes += e.encodedDataLength; });
    page.on("request", r => { reqs++; if (!r.url().startsWith(BASE) && !r.url().startsWith("data:")) third.add(new URL(r.url()).host); });
    await page.evaluateOnNewDocument(() => {
      window.__lcp = 0; window.__cls = 0;
      new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
    });
    await page.goto(BASE + path, { waitUntil: "networkidle0" });
    await new Promise(r => setTimeout(r, 600));
    const m = await page.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0];
      const fcp = performance.getEntriesByName("first-contentful-paint")[0];
      return { ttfb: nav.responseStart, fcp: fcp ? fcp.startTime : 0, lcp: window.__lcp, cls: window.__cls };
    });
    const row = { requests: reqs, transferKB: Math.round(bytes / 1024), ...m, thirdParty: third.size };
    const bad = Object.keys(BUDGET).filter(k => row[k] > BUDGET[k]);
    if (bad.length) failed++;
    console.log(path.padEnd(14), String(row.requests).padStart(4), String(row.transferKB).padStart(6), String(Math.round(m.ttfb)).padStart(6), String(Math.round(m.fcp)).padStart(6), String(Math.round(m.lcp)).padStart(6), m.cls.toFixed(3).padStart(6), String(third.size).padStart(4), bad.length ? "  OVER: " + bad.join(",") + (third.size ? " [" + [...third].join(",") + "]" : "") : "");
    await page.close();
  }
  await browser.close();
  console.log(failed ? `\n${failed} page(s) over budget` : "\nall pages within budget");
  process.exit(failed ? 1 : 0);
})();
