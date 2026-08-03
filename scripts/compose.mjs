#!/usr/bin/env node
// Cross-platform replacement for infra/compose.sh: prefer the `docker compose` plugin and
// fall back to the legacy `docker-compose` binary.
//
// Extra flag (not a docker one): `--stdin <file>` pipes a file into the container command,
// which is how the app-role SQL reaches a psql running inside the db service.

import { spawnSync } from "node:child_process";
import { existsSync, openSync } from "node:fs";
import { resolve } from "node:path";

import { expand, loadEnv } from "./lib/env.mjs";

loadEnv();
const argv = process.argv.slice(2).map(expand);

let stdin = "inherit";
const args = [];
for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === "--stdin") {
    const file = resolve(argv[i + 1]);
    if (!existsSync(file)) {
      console.error(`[compose] no such file: ${file}`);
      process.exit(1);
    }
    stdin = openSync(file, "r");
    i += 1;
    continue;
  }
  args.push(argv[i]);
}

const hasPlugin =
  spawnSync("docker", ["compose", "version"], { stdio: "ignore" }).status === 0;

const [command, prefix] = hasPlugin ? ["docker", ["compose"]] : ["docker-compose", []];
const result = spawnSync(command, [...prefix, ...args], {
  stdio: [stdin, "inherit", "inherit"],
});

if (result.error) {
  console.error(
    "[compose] Docker is not available. Install Docker Desktop (Windows/macOS) or the " +
      "docker.io + docker-compose-plugin packages (Linux).",
  );
  process.exit(1);
}
process.exit(result.status ?? 1);
