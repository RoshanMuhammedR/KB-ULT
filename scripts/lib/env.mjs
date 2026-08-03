// Shared .env loading and placeholder expansion for the repo's Node task runners.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Reads the repo-root .env into process.env. Real environment variables win, so
// `API_PORT=9000 pnpm run dev` still overrides the file.
export function loadEnv() {
  const file = join(REPO, ".env");
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    const quoted = value.length > 1 && (value[0] === '"' || value[0] === "'");
    if (quoted && value[value.length - 1] === value[0]) value = value.slice(1, -1);
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

// Expands `@{VAR:default}`. That spelling is deliberate: neither sh nor cmd.exe touches it,
// so the same package.json string survives both shells intact.
export const expand = (value) =>
  value.replace(/@\{(\w+)(?::([^}]*))?\}/g, (_, name, fallback) => {
    const found = process.env[name];
    return found === undefined || found === "" ? (fallback ?? "") : found;
  });
