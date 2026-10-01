#!/usr/bin/env node
/**
 * Turn on universal links (iOS) / app links (Android) for a domain you control.
 *
 *   node scripts/set-app-domain.js links.example.com --team-id ABCDE12345 --sha256 AA:BB:...
 *
 * Writes to app.json:
 *   expo.extra.appDomain          read by lib/links.ts (resolveDeepLink accepts https://<domain>/...)
 *   expo.ios.associatedDomains    ["applinks:<domain>"]
 *   expo.android.intentFilters    an autoVerify VIEW filter for https://<domain>
 * and prints the two files to host at https://<domain>/.well-known/ (no redirects,
 * Content-Type application/json):
 *   apple-app-site-association    needs your Apple Team ID (developer.apple.com → Membership)
 *   assetlinks.json               needs the SHA-256 of your Play app-signing key
 *                                 (`eas credentials -p android`, or Play Console → App integrity)
 *
 * Native config changed, so the next release needs a new build (the fingerprint
 * changes; an OTA update can't add entitlements). Until then only the custom
 * scheme (`<scheme>://settings`) opens the app. Re-run to change the domain.
 */
const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);
const positional = args.filter((a, i) => !a.startsWith("--") && !(args[i - 1] ?? "").startsWith("--"));
const domain = (positional[0] ?? "").toLowerCase();
const flag = (name) => {
  const i = args.indexOf(name);
  return i === -1 ? "" : (args[i + 1] ?? "");
};
if (!/^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/.test(domain)) {
  console.error("usage: node scripts/set-app-domain.js <domain> [--team-id ABCDE12345] [--sha256 AA:BB:...]");
  process.exit(2);
}
const teamId = flag("--team-id") || "<APPLE_TEAM_ID>";
const sha256 = flag("--sha256") || "<PLAY_APP_SIGNING_SHA256>";

const file = path.resolve(__dirname, "..", "app.json");
const app = JSON.parse(fs.readFileSync(file, "utf8"));
const expo = app.expo;
expo.extra = { ...(expo.extra ?? {}), appDomain: domain };
expo.ios = { ...(expo.ios ?? {}), associatedDomains: [`applinks:${domain}`] };
const others = (expo.android?.intentFilters ?? []).filter((f) => !(f.autoVerify && f.data?.some?.((d) => d.scheme === "https")));
expo.android = {
  ...(expo.android ?? {}),
  intentFilters: [
    ...others,
    {
      action: "VIEW",
      autoVerify: true,
      data: [{ scheme: "https", host: domain }],
      category: ["BROWSABLE", "DEFAULT"],
    },
  ],
};
fs.writeFileSync(file, JSON.stringify(app, null, 2) + "\n");

const bundleId = expo.ios.bundleIdentifier;
const aasa = { applinks: { details: [{ appIDs: [`${teamId}.${bundleId}`], components: [{ "/": "/*" }] }] } };
const assetlinks = [
  {
    relation: ["delegate_permission/common.handle_all_urls"],
    target: { namespace: "android_app", package_name: expo.android.package, sha256_cert_fingerprints: [sha256] },
  },
];
console.log(`app.json updated for https://${domain} (rebuild the app: native config changed).\n`);
console.log(`Host at https://${domain}/.well-known/apple-app-site-association :\n${JSON.stringify(aasa, null, 2)}\n`);
console.log(`Host at https://${domain}/.well-known/assetlinks.json :\n${JSON.stringify(assetlinks, null, 2)}`);
if (teamId.startsWith("<") || sha256.startsWith("<")) console.log("\nFill in the <PLACEHOLDERS> before hosting.");
