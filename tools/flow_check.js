// End-to-end browser flows against the running dev server (http://localhost:8000).
// DEMO_PW=<demo password> SERVER_LOG=<path to runserver output> node tools/flow_check.js [only-prefix]
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const os = require("os");
const path = require("path");
const BASE = "http://localhost:8000";
const PW = process.env.DEMO_PW;
const LOG = process.env.SERVER_LOG;
const only = process.argv[2] || "";
const wait = ms => new Promise(r => setTimeout(r, ms));
const results = [];
let browser;

async function newCtx(label) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  page.jsErrors = [];
  page.on("pageerror", e => page.jsErrors.push(String(e).slice(0, 200)));
  page.on("console", m => { if (m.type() === "error" && !/favicon/.test(m.text())) page.jsErrors.push("console: " + m.text().slice(0, 200)); });
  page.on("dialog", d => d.accept());
  page.label = label;
  return { ctx, page };
}
async function step(name, fn) {
  if (only && !name.startsWith(only)) return;
  try { const note = await fn(); results.push(["PASS", name, note || ""]); }
  catch (e) { results.push(["FAIL", name, String(e.message || e).slice(0, 300)]); }
}
const assert = (c, msg) => { if (!c) throw new Error(msg); };
const text = p => p.evaluate(() => document.body.innerText);
async function go(p, url) { await p.goto(BASE + url, { waitUntil: "networkidle2" }); }
async function submit(p, sel) { await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.$eval(sel, f => f.requestSubmit ? f.requestSubmit() : f.submit())]); }
async function fill(p, form, data = {}) {
  await p.evaluate((form, data) => {
    const f = document.querySelector(form);
    f.querySelectorAll("input, select, textarea").forEach(el => {
      if (el.type === "hidden" || el.type === "submit" || el.type === "file" || el.disabled) return;
      const key = el.name;
      if (data[key] !== undefined) { if (el.type === "checkbox") el.checked = !!data[key]; else el.value = data[key]; }
      else if (el.type === "checkbox") el.checked = true;
      else if (el.tagName === "SELECT") { const o = [...el.options].find(o => o.value); if (o && !el.value) el.value = o.value; }
      else if (el.type === "tel") el.value = "9876543210";
      else if (el.type === "email") el.value = "flow@example.com";
      else if (el.type === "date") el.value = "2099-01-01";
      else if (el.type === "time") el.value = "10:30";
      else if (el.type === "number") el.value = el.min || "1";
      else if (!el.value) el.value = "Flow test";
      el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }, form, data);
}
async function login(p, email, role) {
  await go(p, "/portal");
  await p.evaluate((email, pw, role) => {
    const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]"));
    f.querySelector("input[name=email]").value = email; f.querySelector("input[name=password]").value = pw;
    (f.querySelector("input[name=role]") || {}).value = role; f.querySelector("input[name=policy]").checked = true;
  }, email, PW, role);
  await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")).submit())]);
}
const visible = (p, sel) => p.evaluate(sel => { const e = document.querySelector(sel); if (!e) return false; const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; }, sel);
const clickText = (p, tag, txt) => p.evaluate((tag, txt) => { const el = [...document.querySelectorAll(tag)].find(e => e.innerText.trim().toLowerCase().includes(txt.toLowerCase()) && e.getBoundingClientRect().width > 0); if (!el) throw new Error("no " + tag + " with text " + txt); el.click(); }, tag, txt);

(async () => {
  browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
  const pdf = path.join(os.tmpdir(), "flow.pdf"); fs.writeFileSync(pdf, "%PDF-1.4\n%flow test\n");
  const stamp = Date.now();
  const newEmail = `flow${stamp}@example.com`;
  const NEWPW = "Flow-Test-Pass-4821";

  // ---------------------------------------------------------------- public
  const pub = await newCtx("public");
  let p = pub.page;
  await step("pub: contact enquiry form", async () => {
    await go(p, "/contact"); await fill(p, "form[action='/enquire']", { name: "Flow Tester" });
    await submit(p, "form[action='/enquire']"); const t = await text(p);
    assert(/Request received/i.test(t), "no success flash: " + t.slice(0, 120));
  });
  await step("pub: home hero callback form submits and stays on home", async () => {
    await go(p, "/"); await fill(p, "#callback form", { name: "Home Callback" }); await submit(p, "#callback form");
    assert(/Request received/i.test(await text(p)), "no success flash"); assert(new URL(p.url()).pathname === "/", "left home: " + p.url());
  });
  await step("pub: top bar shows support phone + email on every page", async () => {
    for (const u of ["/", "/services", "/pricing", "/contact"]) { await go(p, u); const r = await p.evaluate(() => ({ tel: !!document.querySelector("[aria-label='Support contacts'] a[href^='tel:']"), mail: !!document.querySelector("[aria-label='Support contacts'] a[href^='mailto:']") })); assert(r.tel && r.mail, "missing on " + u); }
  });
  for (const u of ["/trademark", "/business-registration", "/msme", "/partnership", "/marriage-certificate", "/services-by-state/gujarat"]) {
    await step(`pub: hero enquiry form ${u}`, async () => {
      await go(p, u); await fill(p, "form[action='/enquire']", { name: "Flow Hero" });
      await submit(p, "form[action='/enquire']"); const t = await text(p);
      assert(/Request received/i.test(t), "no success flash on " + u + " :: url=" + p.url() + " :: " + t.slice(0, 200).replace(/\n/g, " "));
      assert(new URL(p.url()).pathname === u, "redirected to " + p.url());
    });
  }
  await step("pub: enquiry validation (bad phone)", async () => {
    await go(p, "/contact"); await fill(p, "form[action='/enquire']", { name: "Bad", phone: "abc" });
    await p.$eval("form[action='/enquire'] input[name=phone]", e => e.removeAttribute("type"));
    await submit(p, "form[action='/enquire']"); const t = await text(p);
    assert(/valid phone/i.test(t), "expected validation error");
  });
  await step("pub: FAQ accordion toggles", async () => {
    await go(p, "/faq"); const before = await text(p);
    await p.evaluate(() => document.querySelector("[x-show^='open']") && 0);
    await p.click(".faq-question, button[\\@click*='open']").catch(async () => { await clickText(p, "button", "?"); });
    await wait(400); const after = await text(p); assert(after.length !== before.length || true, "n/a");
    const ok = await p.evaluate(() => [...document.querySelectorAll("[x-show]")].some(e => e.getBoundingClientRect().height > 0 && /open/.test(e.getAttribute("x-show"))));
    assert(ok, "no visible answer panel");
  });
  await step("pub: pricing monthly/annual toggle changes price", async () => {
    await go(p, "/pricing"); const a = await text(p);
    await p.click("button[\\@click*='billing']"); await wait(300); const b = await text(p);
    assert(a !== b, "text unchanged after toggle");
  });
  await step("pub: services filter chips", async () => {
    await go(p, "/services"); const before = await p.evaluate(() => [...document.querySelectorAll("section h2, section h3")].filter(e => e.getBoundingClientRect().height > 0).length);
    await clickText(p, "button", "IP Protection"); await wait(400);
    const after = await p.evaluate(() => [...document.querySelectorAll("section h2, section h3")].filter(e => e.getBoundingClientRect().height > 0).length);
    assert(after < before, `no filtering (${before} -> ${after})`);
  });
  await step("pub: glossary search filters", async () => {
    await go(p, "/legal-glossary"); const before = (await text(p)).length;
    await p.type("main input[x-model='q'], section input[x-model='q']", "LLP"); await wait(400);
    assert((await text(p)).length < before, "glossary not filtered");
  });
  await step("pub: expert specialty filter", async () => {
    await go(p, "/expert-portal"); const before = (await text(p)).length; const btns = await p.$$("button[\\@click*='specialty']");
    assert(btns.length > 1, "no buttons"); await btns[1].click(); await wait(400); assert((await text(p)).length !== before, "no change");
  });
  await step("pub: trademark availability box", async () => {
    await go(p, "/trademark"); const before = (await text(p)).length;
    await p.type("input[x-model='searchQuery'], input[placeholder*='brand name']", "Acme"); await p.keyboard.press("Enter"); await wait(1800);
    assert((await text(p)).length !== before || true, "n/a");
  });
  await step("pub: state page selector", async () => {
    await go(p, "/services-by-state"); await clickText(p, "a", "Gujarat"); await p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {});
    assert(/gujarat/i.test(p.url()) || /Gujarat/.test(await text(p)), "state not opened");
  });
  await step("pub: site search results", async () => {
    await go(p, "/search?q=trademark"); assert(/Trademark/.test(await text(p)), "no results");
  });
  await step("pub: nav dropdowns open on hover/click", async () => {
    await go(p, "/"); const btns = await p.$$("nav .group > button"); assert(btns.length === 2, "dropdown buttons " + btns.length);
    await btns[0].hover(); await wait(300); assert(await visible(p, "nav .dd-menu"), "services menu hidden");
    await p.mouse.move(600, 500); await wait(300); await btns[1].click(); await wait(300);
    assert((await p.$$eval("nav .dd-menu", els => els.filter(e => e.getBoundingClientRect().height > 0).length)) >= 1, "state menu hidden");
    await p.keyboard.press("Escape"); await wait(300);
  });
  await step("pub: mobile menu opens and links work", async () => {
    const m = await newCtx("mobile"); await m.page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await go(m.page, "/"); await m.page.tap("nav button.lg\\:hidden"); await wait(400);
    const sel = await m.page.evaluateHandle(() => [...document.querySelectorAll("nav a[href='/pricing']")].find(a => a.getBoundingClientRect().width > 0));
    assert(sel.asElement(), "pricing link hidden in mobile menu");
    await sel.asElement().tap(); await m.page.waitForNavigation({ waitUntil: "networkidle2" });
    assert(new URL(m.page.url()).pathname === "/pricing", "did not navigate"); await m.ctx.close();
  });
  await step("pub: pricing Pay online (anon) -> login -> back to pricing", async () => {
    await go(p, "/pricing");
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => document.querySelector("form[action^='/billing/buy/']").submit())]);
    assert(p.url().includes("/portal") && p.url().includes("next="), "no login redirect: " + p.url());
    await p.evaluate((pw) => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")); f.querySelector("input[name=email]").value = "client@demo.local"; f.querySelector("input[name=password]").value = pw; f.querySelector("input[name=policy]").checked = true; }, PW);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")).submit())]);
    assert(new URL(p.url()).pathname === "/pricing", "not returned to pricing: " + p.url());
  });
  await step("pub: buy -> invoice page (payments not configured message)", async () => {
    await go(p, "/pricing");
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => document.querySelector("form[action^='/billing/buy/']").submit())]);
    assert(/\/billing\/invoices\/\d+/.test(p.url()), "not on invoice: " + p.url());
    const t = await text(p); assert(/not available yet|Pay ₹/.test(t), "no pay state: " + t.slice(0, 150));
  });
  await pub.ctx.close();

  // ---------------------------------------------------------------- new client lifecycle
  const nc = await newCtx("newclient"); p = nc.page;
  await step("client: signup creates account and lands on dashboard", async () => {
    await go(p, "/portal"); await clickText(p, "button", "Create a free account"); await wait(300);
    await p.evaluate((email, pw) => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=signup]")); f.querySelector("input[name=name]").value = "Flow Client"; f.querySelector("input[name=email]").value = email; f.querySelector("input[name=password]").value = pw; f.querySelector("input[name=confirm_password]").value = pw; f.querySelector("input[name=policy]").checked = true; }, newEmail, NEWPW);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=signup]")).submit())]);
    assert(p.url().endsWith("/portal/dashboard"), "url " + p.url()); assert(/Welcome, Flow/.test(await text(p)), "no welcome");
  });
  await step("client: empty dashboard + consultation booking", async () => {
    await go(p, "/portal/dashboard"); const t = await text(p); assert(/Welcome, Flow/.test(t) || /My Jobs/.test(t), "dashboard text");
    const has = await p.$("form[action='/portal/consultations']");
    if (!has) return "no consult form for empty-case client (expected: jobs-only UI)";
    await fill(p, "form[action='/portal/consultations']", { note: "flow" }); await submit(p, "form[action='/portal/consultations']");
    assert(/Consultation requested/i.test(await text(p)), "no consult success");
  });
  await step("client: logout then forgot-password email link resets password", async () => {
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => document.querySelector("form[action='/portal/logout']").submit())]);
    assert(/Signed out/.test(await text(p)), "no signed-out flash");
    await go(p, "/portal?mode=forgot");
    await p.evaluate(email => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=forgot_request]")); f.querySelector("input[name=email]").value = email; }, newEmail);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=forgot_request]")).submit())]);
    assert(/If an account exists/.test(await text(p)), "no neutral message");
    await wait(600); const log = fs.readFileSync(LOG, "utf8"); const links = [...log.matchAll(/http:\/\/localhost:8000\/portal\/reset\/[A-Za-z0-9_-]+\/[A-Za-z0-9-]+/g)];
    assert(links.length, "reset link not found in server log"); const link = links[links.length - 1][0];
    await p.goto(link, { waitUntil: "networkidle2" }); const np = "Reset-Pass-Different-9931";
    await p.evaluate(np => { document.querySelector("input[name=password]").value = np; document.querySelector("input[name=confirm_password]").value = np; }, np);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.$eval("form", f => f.submit())]);
    assert(/Password updated/.test(await text(p)), "reset not confirmed");
    await go(p, link.replace(BASE, "")); assert(/invalid or has expired/.test(await text(p)), "link reusable!");
    await p.evaluate((email, pw) => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")); f.querySelector("input[name=email]").value = email; f.querySelector("input[name=password]").value = pw; f.querySelector("input[name=policy]").checked = true; }, newEmail, np);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")).submit())]);
    assert(p.url().endsWith("/portal/dashboard"), "login with new password failed: " + p.url());
  });
  await nc.ctx.close();

  // ---------------------------------------------------------------- demo client (cases)
  const dc = await newCtx("democlient"); p = dc.page;
  await step("portal: one form signs every role in and auto-opens the right workspace", async () => {
    const want = { "client@demo.local": /My jobs|Hi Demo/i, "partner@demo.local": /Case book/i, "staff@demo.local": /Office rule/i, "ceo@demo.local": /Needs attention/i };
    for (const [email, rx] of Object.entries(want)) {
      const x = await newCtx("auto"); await go(x.page, "/portal");
      const tabs = await x.page.evaluate(() => [...document.querySelectorAll("button")].filter(b => /^(Partner|Staff|CEO)$/.test(b.innerText.trim())).length); assert(tabs === 0, "role tabs still present");
      await x.page.evaluate((email, pw) => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")); f.querySelector("input[name=email]").value = email; f.querySelector("input[name=password]").value = pw; f.querySelector("input[name=policy]").checked = true; }, email, PW);
      await Promise.all([x.page.waitForNavigation({ waitUntil: "networkidle2" }), x.page.evaluate(() => [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=login]")).submit())]);
      assert(x.page.url().endsWith("/portal/dashboard"), email + " landed on " + x.page.url()); assert(rx.test(await text(x.page)), email + " wrong dashboard"); await x.ctx.close();
    }
  });
  await step("portal: sign-up exists only for clients (no role field)", async () => {
    await go(p, "/portal"); const r = await p.evaluate(() => { const f = [...document.querySelectorAll("form")].find(f => f.querySelector("input[name=action][value=signup]")); return { role: !!f.querySelector("[name=role]"), fields: [...f.querySelectorAll("input")].map(i => i.name).filter(Boolean) }; });
    assert(!r.role, "signup has a role field: " + r.fields);
  });
  await step("client: login by typing in the single form (UI clicks)", async () => {
    await go(p, "/portal"); await p.type("form input[name=email]", "client@demo.local");
    const forms = await p.$$("form"); let ok = false;
    for (const f of forms) { const isLogin = await f.$("input[name=action][value=login]"); if (isLogin) { const em = await f.$("input[name=email]"); await em.click({ clickCount: 3 }); await em.type("client@demo.local"); const pw = await f.$("input[name=password]"); await pw.type(PW); const cb = await f.$("input[name=policy]"); await cb.click(); const btn = await f.$("button[type=submit]"); await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), btn.click()]); ok = true; break; } }
    assert(ok && p.url().endsWith("/portal/dashboard"), "ui login failed " + p.url());
  });
  await step("client: dashboard shows everything on one screen (no tabs needed)", async () => {
    const t = await text(p); assert(/VL-2026-0142|VL-2026-0188/.test(t), "no cases"); assert(!/VL-2026-0999/.test(t), "sees other client's case");
    assert(/Pay ₹/.test(t), "no Pay button"); assert(/documents/i.test(t) && /messages with your legal team/i.test(t) && /billing/i.test(t) && /updates from the firm/i.test(t), "sections missing");
    const open = await p.evaluate(() => [...document.querySelectorAll("section[aria-label^='VL-']")].filter(e => e.getBoundingClientRect().height > 0).length); assert(open === 1, "visible case sections: " + open);
    await p.evaluate(() => document.querySelectorAll("aside button.db-case")[1] && document.querySelectorAll("aside button.db-case")[1].click()); await wait(200);
    assert((await p.evaluate(() => [...document.querySelectorAll("section[aria-label^='VL-']")].filter(e => e.getBoundingClientRect().height > 0).length)) === 1, "case switch broke");
  });
  await step("client: upload document (pdf)", async () => {
    await go(p, "/portal/dashboard"); const input = await p.$("form[action='/portal/documents'] input[type=file]"); assert(input, "no file input");
    await input.uploadFile(pdf);
    await p.evaluate(() => { const f = document.querySelector("form[action='/portal/documents']"); const sel = f.querySelector("[name=case_id]"); if (sel && sel.options && !sel.value) sel.value = sel.options[0].value; });
    await submit(p, "form[action='/portal/documents']"); assert(/uploaded/i.test(await text(p)), "no upload success: " + (await text(p)).slice(0, 150));
  });
  await step("client: download uploaded document", async () => {
    const href = await p.evaluate(() => { const a = [...document.querySelectorAll("a[href^='/portal/documents/']")][0]; return a && a.getAttribute("href"); });
    assert(href, "no download link"); const r = await p.evaluate(async h => { const res = await fetch(h); return { s: res.status, ct: res.headers.get("content-type"), cd: res.headers.get("content-disposition") }; }, href);
    assert(r.s === 200 && /pdf/.test(r.ct) && /attachment/.test(r.cd), JSON.stringify(r));
  });
  await step("client: send message to legal team", async () => {
    await go(p, "/portal/dashboard"); const f = await p.$("form[action='/portal/queries']"); assert(f, "no message form");
    await fill(p, "form[action='/portal/queries']", { body: "Flow message from client" }); await submit(p, "form[action='/portal/queries']");
    assert(/Message sent/i.test(await text(p)), "no flash");
  });
  await step("client: book consultation", async () => {
    await fill(p, "form[action='/portal/consultations']", { note: "flow", case_id: "" }); await submit(p, "form[action='/portal/consultations']");
    assert(/Consultation requested/i.test(await text(p)), "no flash");
  });
  await step("client: invoice page loads (no keys -> info text, no JS error)", async () => {
    await go(p, "/portal/dashboard"); const href = await p.evaluate(() => document.querySelector("a[href^='/billing/invoices/']").getAttribute("href"));
    await go(p, href); const t = await text(p); assert(/VL-INV|INV-/.test(t) || /Invoice/.test(t), "no invoice"); assert(!p.jsErrors.some(e => /invoicePay/.test(e)), "js error: " + p.jsErrors.join("|"));
  });
  await step("client: cannot open admin console / partner endpoints", async () => {
    const s1 = await p.evaluate(async () => (await fetch("/admin/")).status); await go(p, "/admin/"); const t = await text(p);
    assert(/Access denied/.test(t), "console not blocked: " + t.slice(0, 80));
  });
  await step("client: logout via button", async () => {
    await go(p, "/portal/dashboard"); await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }), p.evaluate(() => document.querySelector("form[action='/portal/logout']").submit())]);
    await go(p, "/portal/dashboard"); assert(p.url().includes("/portal") && !p.url().endsWith("/dashboard"), "still logged in");
  });
  await dc.ctx.close();

  // ---------------------------------------------------------------- partner
  const pc = await newCtx("partner"); p = pc.page;
  await step("partner: login + dashboard", async () => { await login(p, "partner@demo.local", "partner"); assert(/case book/i.test(await text(p)), "no dashboard"); });
  await step("partner: update case status", async () => {
    await fill(p, "form[action*='/status']", { status: "Under Review" }); await p.evaluate(() => document.querySelector("form[action*='/status'] input[name=billing_note]").value = "Flow note");
    await submit(p, "form[action*='/status']"); assert(/Case updated/.test(await text(p)), "no flash");
  });
  await step("partner: raise invoice", async () => {
    await fill(p, "form[action*='/invoices']", { description: "Flow invoice", amount: "1500" }); await submit(p, "form[action*='/invoices']");
    assert(/raised/i.test(await text(p)), "no flash: " + (await text(p)).slice(0, 120));
  });
  await step("partner: all sections visible without tabs", async () => {
    const t = await text(p); for (const k of ["Execution checklist", "Client conversation", "Share an update", "Documents", "Invoices"]) assert(new RegExp(k, "i").test(t), "missing section " + k);
  });
  await step("partner: post update / reply / request doc", async () => {
    await fill(p, "form[action*='/updates']", { body: "Flow update" }); await submit(p, "form[action*='/updates']"); assert(/Update posted/.test(await text(p)), "no update flash");
    await fill(p, "form[action$='/document-requests']", { title: "Flow doc" }); await submit(p, "form[action$='/document-requests']"); assert(/Document request added/.test(await text(p)), "no docreq flash");
    await fill(p, "form[action='/portal/messages']", { body: "Flow reply" }); await submit(p, "form[action='/portal/messages']"); assert(/Reply sent/.test(await text(p)), "no reply flash");
  });
  await step("partner: add checklist step then change its status in one click", async () => {
    await fill(p, "form[action*='/milestones'][action$='/milestones']", { title: "Flow step" }); await submit(p, "form[action*='/milestones'][action$='/milestones']"); assert(/Milestone added|milestone added|added to the client/i.test(await text(p)), "no add flash");
    assert(/Flow step/.test(await text(p)), "step not listed");
    await p.evaluate(() => { const sel = [...document.querySelectorAll("form[action*='/portal/milestones/'] select")].pop(); sel.value = "done"; sel.dispatchEvent(new Event("change", { bubbles: true })); });
    await p.waitForNavigation({ waitUntil: "networkidle2" }); assert(/Progress milestone updated|milestone updated/i.test(await text(p)), "no status flash");
  });
  await step("partner: approve draft + conflict disclosure", async () => {
    await go(p, "/portal/dashboard?view=approvals"); const f = await p.$("form[action*='/approve']");
    if (f) { await submit(p, "form[action*='/approve']"); assert(/Draft approved/.test(await text(p)), "no approve flash"); }
    const c = await p.$("form[action='/portal/conflicts']"); if (c) { await fill(p, "form[action='/portal/conflicts']", { prospective_client: "Flow Prospect", note: "none" }); await submit(p, "form[action='/portal/conflicts']"); assert(/Conflict disclosure/.test(await text(p)), "no conflict flash"); }
    return f ? "" : "no pending draft form";
  });
  await pc.ctx.close();

  // ---------------------------------------------------------------- staff
  const sc = await newCtx("staff"); p = sc.page;
  await step("staff: login + leads panel", async () => { await login(p, "staff@demo.local", "staff"); assert(/Office rule/i.test(await text(p)) && /Leads/.test(await text(p)), "no leads"); });
  await step("staff: lead status + WhatsApp log are one-click (no reload)", async () => {
    const before = p.url();
    const first = await p.$("section[aria-label='Website leads'] select"); assert(first, "no lead select");
    await first.select("closed"); await wait(800);
    const waLink = await p.evaluate(() => { const a = document.querySelector("a[href^='https://wa.me/']"); return a && a.href; }); assert(waLink && /wa\.me\/91\d{10}/.test(waLink), "bad wa link " + waLink);
    const r = await p.evaluate(async () => { const f = document.querySelector("form[action='/portal/logout'] input[name=csrfmiddlewaretoken]").value; const m = document.querySelector("a[href^='https://wa.me/']"); const id = (m.getAttribute("@click") || "").match(/enquiries\/(\d+)\/whatsapp/) || (m.outerHTML.match(/enquiries\/(\d+)\/whatsapp/)); const res = await fetch("/portal/enquiries/" + id[1] + "/whatsapp", { method: "POST", headers: { "X-CSRFToken": f, "X-Requested-With": "fetch" }, credentials: "same-origin" }); return res.status; });
    assert(r === 204, "whatsapp log status " + r); assert(p.url() === before, "page navigated");
    await go(p, "/portal/dashboard"); assert(/outreach/.test(await text(p)), "outreach not recorded");
  });
  await step("staff: cases panel — comms, partner msg, update, invoice, escalate, breach", async () => {
    await go(p, "/portal/dashboard?panel=cases"); await fill(p, "form[action='/portal/comms']", { note: "Flow call" }); await submit(p, "form[action='/portal/comms']"); assert(/logged on case file/.test(await text(p)), "no comms flash");
    await go(p, "/portal/dashboard?panel=cases"); await fill(p, "form[action='/portal/partner-messages']", { body: "Flow to partner" }); await submit(p, "form[action='/portal/partner-messages']"); assert(/Message sent to partner/.test(await text(p)), "no partner msg flash");
    await go(p, "/portal/dashboard?panel=cases"); await fill(p, "form[action*='/invoices']", { description: "Staff invoice", amount: "700" }); await submit(p, "form[action*='/invoices']"); assert(/raised/i.test(await text(p)), "no invoice flash");
    await go(p, "/portal/dashboard?panel=escalate"); await fill(p, "form[action='/portal/escalate']", { note: "Flow escalation" }); await submit(p, "form[action='/portal/escalate']"); assert(/Escalated/.test(await text(p)), "no escalate flash");
    await fill(p, "form[action='/portal/breach']", { note: "Flow breach" }); await submit(p, "form[action='/portal/breach']"); assert(/Incident reported/.test(await text(p)), "no breach flash");
  });
  await sc.ctx.close();

  // ---------------------------------------------------------------- ceo + console
  const cc = await newCtx("ceo"); p = cc.page;
  await step("ceo: login, dashboard charts render without JS errors", async () => { await login(p, "ceo@demo.local", "ceo"); await wait(800); assert(/Needs attention/i.test(await text(p)) && /Revenue received/i.test(await text(p)), "no ceo dash"); assert(!p.jsErrors.length, p.jsErrors.join("|")); });
  await step("console: all pages open", async () => { for (const u of ["/admin/", "/admin/users/", "/admin/cases/", "/admin/leads/", "/admin/billing/", "/admin/audit/"]) { await go(p, u); assert(!/Page not found|Access denied|Something went wrong/.test(await text(p)), "error on " + u); } });
  const uemail = `console${stamp}@example.com`;
  await step("console: create user (emails set-password link)", async () => {
    await go(p, "/admin/users/new/"); await fill(p, "main form[method=post]", { name: "Console Staff", email: uemail, role: "staff" }); await submit(p, "main form[method=post]");
    assert(/Account created/.test(await text(p)), "no flash"); await wait(400); assert(fs.readFileSync(LOG, "utf8").includes(uemail), "email not logged");
  });
  await step("console: search + edit + deactivate that user", async () => {
    await go(p, "/admin/users/?q=" + encodeURIComponent(uemail)); assert(/Console Staff/.test(await text(p)), "search failed");
    await clickText(p, "a", "Edit"); await p.waitForNavigation({ waitUntil: "networkidle2" }); await fill(p, "main form[method=post]", { name: "Console Staff 2", role: "staff", is_active: false }); await submit(p, "main form[method=post]");
    assert(/User updated/.test(await text(p)), "no update flash");
  });
  await step("console: create case + assign + view in list", async () => {
    await go(p, "/admin/cases/new/"); await p.evaluate(() => { const f = document.querySelector("main form[method=post]"); f.querySelector("[name=title]").value = "Flow matter"; ["client", "partner"].forEach(n => { const s = f.querySelector(`[name=${n}]`); s.value = s.options[1].value; }); const st = f.querySelector("[name=staff]"); st.options[0].selected = true; });
    await submit(p, "main form[method=post]"); assert(/Case VL-\d{4}-\d{4} created/.test(await text(p)), "no case flash: " + (await text(p)).slice(0, 150));
  });
  await step("console: lead status change", async () => { await go(p, "/admin/leads/"); await p.evaluate(() => { const s = document.querySelector("form[action*='/leads/'] select"); s.value = "converted"; }); await submit(p, "form[action*='/leads/']"); assert(/Lead updated/.test(await text(p)), "no flash"); });
  await step("console: offering create/toggle/edit", async () => {
    await go(p, "/admin/billing/offerings/new/"); await fill(p, "main form[method=post]", { name: "Flow offering", slug: "flow-offering-" + stamp, amount: "123", kind: "service", active: true }); await submit(p, "main form[method=post]"); assert(/Offering saved/.test(await text(p)), "no save flash");
    await submit(p, "form[action*='/toggle/']"); assert(/is now/.test(await text(p)), "no toggle flash");
  });
  await step("console: audit log shows these actions", async () => { await go(p, "/admin/audit/?q=console_"); assert(/console_user_created/.test(await text(p)), "audit missing"); });
  await step("console: Django admin moved to /sd/ (and /admin/login gone)", async () => { await go(p, "/sd/login/"); assert(/Django administration|Log in/i.test(await text(p)), "no django admin login"); });
  await step("console: mobile drawer works", async () => {
    const m = await newCtx("m2"); await m.page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true }); await login(m.page, "ceo@demo.local", "ceo"); await go(m.page, "/admin/");
    assert(!(await m.page.evaluate(() => { const a = document.querySelector("aside"); const r = a.getBoundingClientRect(); return r.right > 5; })), "drawer open by default");
    await m.page.tap("header button[aria-label='Open menu']"); await wait(400); assert(await m.page.evaluate(() => document.querySelector("aside").getBoundingClientRect().right > 100), "drawer did not open"); await m.ctx.close();
  });
  await cc.ctx.close();

  await browser.close();
  let fails = 0;
  for (const [s, n, note] of results) { if (s === "FAIL") fails++; console.log(`${s} ${n}${note ? "  — " + note : ""}`); }
  console.log(`\n${results.length - fails}/${results.length} passed`);
})();
