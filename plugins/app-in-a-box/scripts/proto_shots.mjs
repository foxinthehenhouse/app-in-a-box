#!/usr/bin/env node
// Screenshots of the rendered prototype for the design critique: every screen and
// sheet, light and dark, plus the first screen with reduced motion, cropped to the
// phone at 390x844. The critic reads the PNGs (any agent that can read images:
// Claude Code, Codex), so the review looks at what the founder will see, not the spec.
//
//   node "$KIT/scripts/proto_shots.mjs" design/prototype.html design/shots
//
// Needs Playwright (`playwright` or `playwright-core`, local or global) and a Chromium.
// Without it, exits 3 and says so: take the same shots with your own browser tool
// (Claude in Chrome, a DevTools or Playwright MCP, Codex's browser) instead.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [, , html, outDir = "design/shots"] = process.argv;
if (!html || !fs.existsSync(html)) {
  console.error("usage: proto_shots.mjs <prototype.html> [out dir]");
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

const pw = loadPlaywright();
if (!pw) {
  console.error("proto_shots: Playwright isn't installed. Take the same shots with your browser tool instead " +
    "(each screen and sheet at 390x844, light and dark, and one with reduced motion).");
  process.exit(3);
}

fs.mkdirSync(outDir, { recursive: true });
const url = pathToFileURL(path.resolve(html)).href;
const args = process.getuid && process.getuid() === 0 ? ["--no-sandbox"] : [];
const browser = await pw.chromium.launch({ args });
const written = [];
const errors = [];

async function session(reducedMotion) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url);
  await page.waitForTimeout(1600);
  return { ctx, page };
}

async function shot(page, name) {
  await page.waitForTimeout(1400); // let the entrance settle: critique the resting state
  const file = path.join(outDir, `${name}.png`);
  await page.locator("#phone").screenshot({ path: file, animations: "disabled" });
  written.push(file);
}

{
  const { ctx, page } = await session("no-preference");
  const spec = await page.evaluate(() => window.__proto && JSON.parse(document.getElementById("proto-spec").textContent));
  for (const mode of ["light", "dark"]) {
    await page.evaluate((m) => document.querySelector(`input[name="p-mode"][value="${m}"]`).click(), mode);
    for (const s of spec.screens) {
      await page.evaluate((id) => window.__proto.act({ go: id }), s.id);
      await shot(page, `${mode}-${s.id}`);
    }
    for (const sh of spec.sheets || []) {
      await page.evaluate((id) => window.__proto.act({ sheet: id }), sh.id);
      await shot(page, `${mode}-sheet-${sh.id}`);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }
  }
  await ctx.close();
}
{
  const { ctx, page } = await session("reduce");
  await shot(page, "reduced-motion-first-screen");
  await ctx.close();
}
await browser.close();
console.log(written.join("\n"));
if (errors.length) {
  console.error("page errors (a kit bug: report it):\n  " + errors.join("\n  "));
  process.exit(1);
}
