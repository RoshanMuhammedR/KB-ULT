#!/usr/bin/env node
// Map local dev domains to 127.0.0.1 so the Saga two-app domain-handoff flow is testable
// on localhost. The marketing site runs at the first domain, and each additional domain is a
// tenant workspace you can register/log into on the product app.
//
//   Marketing (website) : http://saga.test:${WEBSITE_PORT:-3001}
//   Product (per tenant): http://<domain>:${WEB_PORT:-3000}   e.g. http://acme.test:3000
//
// Usage:
//   pnpm run domains:map     # add the managed block to the hosts file
//   pnpm run domains:unmap   # remove the managed block
//
// Editing the hosts file needs root/Administrator, so run this from an elevated terminal on
// Windows; on macOS/Linux it re-runs itself through sudo.
//
// Edit DOMAINS below to add your own tenant domains, then re-run. CORS on the API already
// allows any *.test host (see cors_allowed_origin_regex), so no backend edit is needed.

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// --- Edit this list ---------------------------------------------------------
const DOMAINS = ["saga.test", "acme.test", "admin.test", "roshan.test"];
// ---------------------------------------------------------------------------

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const IS_WIN = process.platform === "win32";
const HOSTS_FILE = IS_WIN
  ? join(process.env.SystemRoot || "C:\\Windows", "System32", "drivers", "etc", "hosts")
  : "/etc/hosts";
const BEGIN = "# >>> saga dev domains >>>";
const END = "# <<< saga dev domains <<<";

// The .env values matter only for the summary printed at the end.
function envValue(key, fallback) {
  if (process.env[key]) return process.env[key];
  const file = join(REPO, ".env");
  if (!existsSync(file)) return fallback;
  const match = readFileSync(file, "utf8").match(new RegExp(`^${key}=(.*)$`, "m"));
  return match ? match[1].trim() : fallback;
}

const remove = process.argv[2] === "--remove" || process.argv[2] === "-r";
const eol = IS_WIN ? "\r\n" : "\n";

function stripBlock(text) {
  const lines = text.split(/\r?\n/);
  const out = [];
  let inside = false;
  for (const line of lines) {
    if (line.trim() === BEGIN) inside = true;
    else if (line.trim() === END) inside = false;
    else if (!inside) out.push(line);
  }
  return out.join(eol).replace(/(\r?\n)+$/, "") + eol;
}

function write(contents) {
  try {
    writeFileSync(HOSTS_FILE, contents);
    return true;
  } catch (error) {
    if (error.code !== "EACCES" && error.code !== "EPERM") throw error;
    return false;
  }
}

const current = existsSync(HOSTS_FILE) ? readFileSync(HOSTS_FILE, "utf8") : "";
let next = stripBlock(current);

if (!remove) {
  const block = [BEGIN, ...DOMAINS.flatMap((d) => [`127.0.0.1 ${d}`, `::1 ${d}`]), END];
  next += block.join(eol) + eol;
}

if (!write(next)) {
  if (IS_WIN) {
    console.error(
      `\nCannot write ${HOSTS_FILE} — Administrator rights are required.\n` +
        "Re-run this from an elevated terminal:\n" +
        `  Start-Process powershell -Verb RunAs -ArgumentList '-NoExit','-Command','cd ${REPO}; pnpm run ${remove ? "domains:unmap" : "domains:map"}'\n`,
    );
    process.exit(1);
  }
  // POSIX: retry the whole script under sudo, which prompts on the terminal.
  const elevated = spawnSync(
    "sudo",
    [process.execPath, fileURLToPath(import.meta.url), ...process.argv.slice(2)],
    { stdio: "inherit" },
  );
  process.exit(elevated.status ?? 1);
}

if (remove) {
  console.log("Done. Local domain mappings removed.");
  process.exit(0);
}

const websitePort = envValue("WEBSITE_PORT", "3001");
const webPort = envValue("WEB_PORT", "3000");

console.log("\nMapped:");
DOMAINS.forEach((domain, index) => {
  const target =
    index === 0
      ? `marketing site : http://${domain}:${websitePort}`
      : `product app    : http://${domain}:${webPort}`;
  console.log(`  \u2022 ${domain}  \u2192 ${target}`);
});
console.log("\nStart everything with:  pnpm run dev");
console.log(`Then open:              http://${DOMAINS[0]}:${websitePort}\n`);
