import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const useLinuxCache = process.platform === "linux" && (Boolean(process.env.WSL_DISTRO_NAME) || projectRoot.startsWith("/mnt/"));
const cacheRoot = resolve(process.env.SPANTRACE_WEB_BUILD_CACHE || join(homedir(), ".cache", "spantrace", "web-build"));
const buildStateName = ".spantrace-build-state.json";
const productionDistDir = ".next-build";

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", env: process.env });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

async function copySourceToCache() {
  await mkdir(cacheRoot, { recursive: true });
  for (const directory of ["app", "lib", "public"]) {
    await rm(join(cacheRoot, directory), { recursive: true, force: true });
    if (existsSync(join(projectRoot, directory))) await cp(join(projectRoot, directory), join(cacheRoot, directory), { recursive: true });
  }
  for (const file of ["package.json", "package-lock.json", "next.config.ts", "next-env.d.ts", "tsconfig.json"]) {
    await cp(join(projectRoot, file), join(cacheRoot, file));
  }
}

async function ensureDependencies() {
  const lockfile = await readFile(join(cacheRoot, "package-lock.json"));
  const fingerprint = createHash("sha256").update(lockfile).digest("hex");
  const fingerprintPath = join(cacheRoot, ".lock.sha256");
  let previous = "";
  try { previous = (await readFile(fingerprintPath, "utf8")).trim(); } catch { /* first cached build */ }
  if (!existsSync(join(cacheRoot, "node_modules", "next", "dist", "bin", "next")) || previous !== fingerprint) {
    console.log("Installing web dependencies in the Linux build cache (one-time or after package-lock changes)…");
    run("npm", ["ci", "--ignore-scripts"], cacheRoot);
    await writeFile(fingerprintPath, fingerprint);
  }
}

async function sourceFingerprint(root) {
  const hash = createHash("sha256");
  const files = [];
  const roots = ["app", "lib", "public", "scripts"];
  const rootFiles = ["package.json", "package-lock.json", "next.config.ts", "next-env.d.ts", "tsconfig.json"];

  async function walk(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === ".next" || entry.name === ".git") continue;
      const fullPath = join(directory, entry.name);
      if (entry.isDirectory()) await walk(fullPath);
      else if (entry.isFile()) files.push(fullPath);
    }
  }

  for (const directory of roots) {
    const fullPath = join(root, directory);
    if (existsSync(fullPath)) await walk(fullPath);
  }
  for (const file of rootFiles) {
    const fullPath = join(root, file);
    if (existsSync(fullPath)) files.push(fullPath);
  }
  files.sort();
  for (const file of files) {
    hash.update(relative(root, file).replaceAll("\\", "/"));
    hash.update(await readFile(file));
  }
  return hash.digest("hex");
}

async function hasCurrentBuild(root, fingerprint) {
  const buildDirectory = join(root, productionDistDir);
  if (!existsSync(join(buildDirectory, "BUILD_ID"))) return false;
  try {
    const state = JSON.parse(await readFile(join(buildDirectory, buildStateName), "utf8"));
    return state.fingerprint === fingerprint;
  } catch {
    return false;
  }
}

async function recordBuild(root, fingerprint) {
  await writeFile(join(root, productionDistDir, buildStateName), JSON.stringify({ fingerprint, recordedAt: new Date().toISOString() }) + "\n");
}

async function main() {
  const fingerprint = await sourceFingerprint(projectRoot);
  const forceBuild = process.env.SPANTRACE_FORCE_BUILD === "1";
  if (!useLinuxCache) {
    if (!forceBuild && await hasCurrentBuild(projectRoot, fingerprint)) {
      console.log("Production build is up to date. Set SPANTRACE_FORCE_BUILD=1 to rebuild.");
      return;
    }
    run(process.execPath, [join(projectRoot, "node_modules", "next", "dist", "bin", "next"), "build", ...process.argv.slice(2)], projectRoot);
    await recordBuild(projectRoot, fingerprint);
    return;
  }
  if (!forceBuild && await hasCurrentBuild(cacheRoot, fingerprint)) {
    console.log("Production build cache is up to date. Set SPANTRACE_FORCE_BUILD=1 to rebuild.");
    return;
  }
  await copySourceToCache();
  await ensureDependencies();
  console.log(`Building from the Linux filesystem cache: ${cacheRoot}`);
  run(process.execPath, [join(cacheRoot, "node_modules", "next", "dist", "bin", "next"), "build", ...process.argv.slice(2)], cacheRoot);
  await recordBuild(cacheRoot, fingerprint);
}

await main();
