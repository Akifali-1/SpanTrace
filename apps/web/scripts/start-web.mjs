import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const useLinuxCache = process.platform === "linux" && (Boolean(process.env.WSL_DISTRO_NAME) || projectRoot.startsWith("/mnt/"));
const cacheRoot = resolve(process.env.SPANTRACE_WEB_BUILD_CACHE || join(homedir(), ".cache", "spantrace", "web-build"));
const runtimeRoot = useLinuxCache ? cacheRoot : projectRoot;
const productionDistDir = ".next-build";
const nextBin = join(runtimeRoot, "node_modules", "next", "dist", "bin", "next");

if (!existsSync(join(runtimeRoot, productionDistDir, "BUILD_ID"))) {
  console.error("No production build found. Run npm run build first.");
  process.exit(1);
}

const result = spawnSync(process.execPath, [nextBin, "start", "--port", "3070"], { cwd: runtimeRoot, stdio: "inherit", env: process.env });
if (result.error) throw result.error;
process.exit(result.status || 0);
