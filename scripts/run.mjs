#!/usr/bin/env node
// Cross-platform task runner for the pnpm scripts in this repo.
//
// The scripts used to be POSIX-only (`. .venv/bin/activate`, `set -a; . ./.env`, `cp`),
// which cannot run through cmd.exe on Windows. Everything shell-specific now lives here
// instead, so `package.json` only ever invokes `node scripts/run.mjs ...`.
//
// Commands:
//   ensure-env               copy .env.example -> .env when .env is missing
//   setup-venv               create apps/api/.venv with a Python >= 3.11 and install the API
//   venv [--cwd d] cmd...    run a binary from the API virtualenv (alembic, uvicorn, ...)
//   exec [--cwd d] cmd...    run a node_modules/.bin binary (turbo, next, ...)
//   psql [args...]           run psql against the local database from .env
//
// Arguments may contain `@{VAR:default}` placeholders, expanded from .env here. That
// spelling is deliberate: neither sh nor cmd.exe touches it, so the same string survives
// both shells intact.

import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import { REPO, expand, loadEnv } from "./lib/env.mjs";

const IS_WIN = process.platform === "win32";
const API_DIR = join(REPO, "apps", "api");
const VENV_DIR = join(API_DIR, ".venv");
const VENV_BIN = join(VENV_DIR, IS_WIN ? "Scripts" : "bin");
// Oldest interpreter the API supports (apps/api/pyproject.toml: requires-python >= 3.11).
const MIN_PY = [3, 11];

function fail(message) {
  console.error(`\n[run.mjs] ${message}\n`);
  process.exit(1);
}

// --- process helpers -------------------------------------------------------

function exec(command, args, cwd) {
  // .cmd/.bat shims (pnpm puts those in node_modules/.bin on Windows) are not executables,
  // so they only start through a shell.
  const needsShell = IS_WIN && /\.(cmd|bat)$/i.test(command);
  const result = spawnSync(command, args, {
    stdio: "inherit",
    cwd: cwd || REPO,
    env: process.env,
    shell: needsShell,
  });
  if (result.error) fail(`failed to start ${command}: ${result.error.message}`);
  process.exit(result.status ?? 1);
}

function capture(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", shell: false });
  return result.status === 0 ? (result.stdout || "").trim() : null;
}

// Pull `--cwd <dir>` off the front of the argument list.
function takeCwd(args) {
  if (args[0] === "--cwd") return { cwd: join(REPO, args[1]), rest: args.slice(2) };
  return { cwd: REPO, rest: args };
}

// --- binary lookup ---------------------------------------------------------

function withWindowsSuffix(base) {
  return IS_WIN ? [`${base}.exe`, `${base}.cmd`, `${base}.bat`, base] : [base];
}

function venvBin(name) {
  for (const candidate of withWindowsSuffix(join(VENV_BIN, name))) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

// Walk up from `cwd` looking for node_modules/.bin/<name>, the way a shell would.
function nodeBin(name, cwd) {
  let dir = resolve(cwd);
  for (;;) {
    for (const candidate of withWindowsSuffix(join(dir, "node_modules", ".bin", name))) {
      if (existsSync(candidate)) return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

// --- python ----------------------------------------------------------------

function pythonVersion(command, args) {
  const out = capture(command, [...args, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"]);
  if (!out) return null;
  const parts = out.split(".").map(Number);
  return parts.length === 2 && parts.every(Number.isInteger) ? parts : null;
}

function findPython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push([process.env.PYTHON, []]);
  if (IS_WIN) {
    // The py launcher is the reliable way to pick a version; fall back to per-user installs
    // because the launcher is a machine-wide component that may not be present.
    for (const v of ["3.13", "3.12", "3.11"]) candidates.push(["py", [`-${v}`]]);
    const localPrograms = join(process.env.LOCALAPPDATA || "", "Programs", "Python");
    if (existsSync(localPrograms)) {
      for (const entry of readdirSync(localPrograms).sort().reverse()) {
        candidates.push([join(localPrograms, entry, "python.exe"), []]);
      }
    }
  }
  for (const name of ["python3.13", "python3.12", "python3.11", "python3", "python"]) {
    candidates.push([name, []]);
  }

  const seen = [];
  for (const [command, args] of candidates) {
    const version = pythonVersion(command, args);
    if (!version) continue;
    seen.push(`${command} ${args.join(" ")}`.trim() + ` -> ${version.join(".")}`);
    if (version[0] > MIN_PY[0] || (version[0] === MIN_PY[0] && version[1] >= MIN_PY[1])) {
      return { command, args, version };
    }
  }
  fail(
    `no Python >= ${MIN_PY.join(".")} found (the API requires it).\n` +
      (seen.length ? `Interpreters checked:\n  ${seen.join("\n  ")}\n` : "") +
      "Install one, or point PYTHON at it:\n" +
      "  Windows : winget install --id Python.Python.3.12 --source winget\n" +
      "  macOS   : brew install python@3.12\n" +
      "  Linux   : sudo apt install python3.12 python3.12-venv",
  );
}

// --- postgres --------------------------------------------------------------

function findPsql() {
  const onPath = capture(IS_WIN ? "where" : "which", ["psql"]);
  if (onPath) return onPath.split(/\r?\n/)[0].trim();
  if (IS_WIN) {
    // EDB installs land here and are not added to PATH by default.
    for (const root of ["C:\\Program Files\\PostgreSQL", "C:\\Program Files (x86)\\PostgreSQL"]) {
      if (!existsSync(root)) continue;
      const versions = readdirSync(root).sort((a, b) => Number(b) - Number(a));
      for (const version of versions) {
        const candidate = join(root, version, "bin", "psql.exe");
        if (existsSync(candidate)) return candidate;
      }
    }
  }
  fail(
    "psql not found on PATH.\n" +
      "  Windows : add C:\\Program Files\\PostgreSQL\\<version>\\bin to PATH\n" +
      "  macOS   : brew install libpq && brew link --force libpq\n" +
      "  Linux   : sudo apt install postgresql-client",
  );
}

const databaseUrl = () => {
  const user = process.env.POSTGRES_USER || "kb_user";
  const password = process.env.POSTGRES_PASSWORD || "kb_password";
  const port = process.env.POSTGRES_PORT || "5432";
  const name = process.env.POSTGRES_DB || "kb_new";
  const host = process.env.POSTGRES_HOST || "localhost";
  return `postgresql://${encodeURIComponent(user)}:${encodeURIComponent(password)}@${host}:${port}/${name}`;
};

// --- commands --------------------------------------------------------------

const commands = {
  "ensure-env"() {
    const target = join(REPO, ".env");
    if (existsSync(target)) {
      console.log(".env already exists — leaving it untouched.");
      return;
    }
    copyFileSync(join(REPO, ".env.example"), target);
    console.log("Created .env from .env.example — fill in AICREDITS_API_KEY and FILEBASE_* next.");
  },

  "setup-venv"() {
    if (!venvBin("python")) {
      const python = findPython();
      console.log(`Creating ${VENV_DIR} with Python ${python.version.join(".")}`);
      const created = spawnSync(python.command, [...python.args, "-m", "venv", ".venv"], {
        stdio: "inherit",
        cwd: API_DIR,
      });
      if (created.status !== 0) fail("could not create the virtualenv");
    }
    const python = venvBin("python") || fail("virtualenv is missing a python executable");
    for (const args of [
      ["-m", "pip", "install", "--upgrade", "pip"],
      ["-m", "pip", "install", "-e", "."],
    ]) {
      const result = spawnSync(python, args, { stdio: "inherit", cwd: API_DIR });
      if (result.status !== 0) fail(`pip step failed: ${args.join(" ")}`);
    }
    console.log("API dependencies installed.");
  },

  venv(argv) {
    const { cwd, rest } = takeCwd(argv);
    if (!rest.length) fail("usage: run.mjs venv [--cwd dir] <command> [args...]");
    const [name, ...args] = rest.map(expand);
    const binary =
      venvBin(name) ||
      fail(`'${name}' is not in the API virtualenv. Run 'pnpm run setup' first.`);
    exec(binary, args, cwd);
  },

  exec(argv) {
    const { cwd, rest } = takeCwd(argv);
    if (!rest.length) fail("usage: run.mjs exec [--cwd dir] <command> [args...]");
    const [name, ...args] = rest.map(expand);
    exec(nodeBin(name, cwd) || name, args, cwd);
  },

  psql(argv) {
    exec(findPsql(), [databaseUrl(), ...argv.map(expand)], REPO);
  },
};

loadEnv();
const [name, ...argv] = process.argv.slice(2);
const command = commands[name];
if (!command) {
  fail(`unknown command '${name ?? ""}'. Available: ${Object.keys(commands).join(", ")}`);
}
command(argv);
