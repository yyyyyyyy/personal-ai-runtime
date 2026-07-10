/**
 * Run electron-builder with Windows-friendly retries for EPERM rename races.
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { cleanDistOutput } = require("./clean-dist-utils");

const ROOT = __dirname;
const DEFAULT_OUTPUT_DIR =
  process.env.DESKTOP_BUILD_OUTPUT ||
  path.join(os.homedir(), ".cache", "personal-ai-runtime-desktop", "dist");
const PATCH = path.join(ROOT, "patch-fs-rename.js");
const CLI = path.join(ROOT, "node_modules", "electron-builder", "out", "cli", "cli.js");

function resolveOutputDir() {
  try {
    cleanDistOutput(DEFAULT_OUTPUT_DIR, "[build-desktop]");
    return DEFAULT_OUTPUT_DIR;
  } catch (err) {
    const fallback = path.join(path.dirname(DEFAULT_OUTPUT_DIR), `dist-${Date.now()}`);
    fs.mkdirSync(fallback, { recursive: true });
    console.warn("[build-desktop] Could not clean default output dir:", err.message);
    console.warn(`[build-desktop] Using fallback output dir: ${fallback}`);
    return fallback;
  }
}

function runBuilder(outputDir) {
  return spawnSync(
    process.execPath,
    ["-r", PATCH, CLI, "--config", "electron-builder.config.js"],
    {
      cwd: ROOT,
      stdio: "inherit",
      env: {
        ...process.env,
        DESKTOP_BUILD_OUTPUT: outputDir,
        ELECTRON_BUILDER_CACHE: process.env.ELECTRON_BUILDER_CACHE || path.join(outputDir, ".cache"),
      },
    },
  );
}

const outputDir = resolveOutputDir();
const result = runBuilder(outputDir);
if (result.status === 0) {
  console.log(`[build-desktop] Artifacts in ${outputDir}`);
  process.exit(0);
}

console.error(
  "[build-desktop] electron-builder failed. On Windows, add antivirus exclusions for the repo and " +
    `${outputDir}, then retry.`,
);
process.exit(result.status || 1);
