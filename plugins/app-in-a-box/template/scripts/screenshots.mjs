#!/usr/bin/env node
// Screenshots of the real app for the craft review: each route, light and dark, at
// phone size (390x844), from a web export in demo mode. scripts/screenshots.sh builds
// the export and calls this; run that, not this. The same approach as the App in a Box
// prototype shots: Playwright (local or global) driving Chromium, PNGs an agent reads.
//
//   node scripts/screenshots.mjs <web export dir> <out dir> <route>...
//
// Signed-out routes (under app/(auth)/) are shot first; then it signs in through the
// demo sign-in screen (any email, any 6 digits) and moves between routes client-side,
// because a page load would reset the in-memory demo session.
// Exit 0 with one PNG per route and mode, 1 on a route that never rendered, 2 on bad
// usage, 3 when Playwright or its Chromium isn't installed (say so; don't fake it).
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const [, , dist, outDir, ...routes] = process.argv;
if (!dist || !outDir || !routes.length || !fs.existsSync(path.join(dist, "index.html"))) {
  console.error("usage: screenshots.mjs <web export dir (has index.html)> <out dir> <route>...");
  process.exit(2);
}

function loadPlaywright() {
  const roots = [process.cwd()];
  try { roots.push(execSync("npm root -g", { encoding: "utf8" }).trim()); } catch { /* no npm */ }
  for (const root of roots) {
    const req = createRequire(path.join(root, "noop.js"));
    for (const name of ["playwright", "playwright-core"]) {
      try { return req(name); } catch { /* try the next */ }
    }
  }
  return null;
}

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".json": "application/json", ".ico": "image/x-icon", ".ttf": "font/ttf" };

/** A static server over the export with a single-page fallback to index.html. */
function serve(root) {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = path.join(root, path.normalize(rel).replace(/^([/\\])+/, ""));
    if (!file.startsWith(path.resolve(root)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(root, "index.html");
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** `/` -> index, `/settings` -> settings, `/days/today` -> days-today. */
const slug = (route) => route.replace(/^\/+|\/+$/g, "").replace(/\//g, "-") || "index";
const signedOut = (route) => /^\/?sign-in\b/.test(route);

/** Wait for a visible route root (`*-screen` / `*-sheet` testID); fail on the error boundary. */
async function settle(page) {
  await page.waitForFunction(() => {
    const shown = (e) => e.getBoundingClientRect().width > 0;
    const roots = document.querySelectorAll('[data-testid$="-screen"], [data-testid$="-sheet"], [data-testid="root-error-boundary"]');
    return [...roots].some(shown) || null;
  }, null, { timeout: 20000 });
  await page.waitForTimeout(1200); // let the entrance finish: grade the resting state
  if (await page.getByTestId("root-error-boundary").isVisible()) {
    throw new Error("the screen crashed into the error boundary (open it in `npx expo start --web` to see why)");
  }
}

async function signIn(page) {
  await page.getByTestId("signin-email-input").fill("craft@example.com");
  await page.getByTestId("signin-send-button").click();
  await page.getByTestId("signin-code-input").fill("123456");
  await page.getByTestId("signin-verify-button").click();
  await page.getByTestId("signin-screen").waitFor({ state: "detached", timeout: 20000 });
}

async function go(page, route) {
  await page.evaluate((r) => {
    window.history.pushState(null, "", r);
    window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
  }, route);
  await settle(page);
}

async function shootMode(browser, base, mode, written, failed) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: mode, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/");
  await settle(page);
  const ordered = [...routes.filter(signedOut), ...routes.filter((r) => !signedOut(r))];
  let inside = false;
  for (const route of ordered) {
    try {
      if (!signedOut(route) && !inside) { await signIn(page); inside = true; }
      await go(page, route);
      const file = path.join(outDir, `${mode}-${slug(route)}.png`);
      await page.screenshot({ path: file, animations: "disabled" });
      written.push(file);
    } catch (e) {
      failed.push(`${mode} ${route}: ${e.message.split("\n")[0]}`);
      // Start the next route from a fresh load, so one crash doesn't take the rest with it.
      await page.goto(base + "/");
      inside = false;
    }
  }
  if (errors.length) failed.push(`${mode}: page errors: ${errors.slice(0, 3).join(" | ")}`);
  await ctx.close();
}

const pw = loadPlaywright();
if (!pw) {
  console.error("screenshots: Playwright isn't installed (npm i -g playwright && npx playwright install chromium). " +
    "Take the same shots with your browser tool instead: each route at 390x844, light and dark.");
  process.exit(3);
}
// Playwright's own Chromium if it was installed, else the system Chrome (CI runners ship one).
async function launch() {
  const args = process.getuid && process.getuid() === 0 ? ["--no-sandbox"] : [];
  try {
    return await pw.chromium.launch({ args });
  } catch {
    return pw.chromium.launch({ args, channel: "chrome" });
  }
}
let browser;
try {
  browser = await launch();
} catch (e) {
  console.error(`screenshots: no Chromium or Chrome to launch (npx playwright install chromium): ${e.message.split("\n")[0]}`);
  process.exit(3);
}

fs.mkdirSync(outDir, { recursive: true });
const server = await serve(path.resolve(dist));
const base = `http://127.0.0.1:${server.address().port}`;
const written = [];
const failed = [];
for (const mode of ["light", "dark"]) await shootMode(browser, base, mode, written, failed);
await browser.close();
server.close();

for (const f of written) console.log(f);
if (failed.length) {
  console.error("screenshots: some routes didn't render:\n  - " + failed.join("\n  - "));
  process.exit(1);
}
console.error(`screenshots: ${written.length} PNG(s) in ${outDir}`);
