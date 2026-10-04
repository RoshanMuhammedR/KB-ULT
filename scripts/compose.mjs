#!/usr/bin/env node
// Cross-platform replacement for infra/compose.sh: prefer the `docker compose` plugin and
// fall back to the legacy `docker-compose` binary.

import { spawnSync } from "node:child_process";

import { expand, loadEnv } from "./lib/env.mjs";

loadEnv();
const argv = process.argv.slice(2).map(expand);

const hasPlugin =
  spawnSync("docker", ["compose", "version"], { stdio: "ignore" }).status === 0;

const [command, prefix] = hasPlugin ? ["docker", ["compose"]] : ["docker-compose", []];
const result = spawnSync(command, [...prefix, ...argv], { stdio: "inherit" });

if (result.error) {
  console.error(
    "[compose] Docker is not available. Install Docker Desktop (Windows/macOS) or the " +
      "docker.io + docker-compose-plugin packages (Linux).",
  );
  process.exit(1);
}
process.exit(result.status ?? 1);
