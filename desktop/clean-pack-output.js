/**
 * Remove stale electron-builder unpack dirs before packaging.
 * Prevents Windows EPERM on rename(win-unpacked.tmp -> win-unpacked).
 */
const path = require("path");
const os = require("os");
const { cleanDistOutput } = require("./clean-dist-utils");

const distDir =
  process.env.DESKTOP_BUILD_OUTPUT ||
  path.join(os.homedir(), ".cache", "personal-ai-runtime-desktop", "dist");

try {
  cleanDistOutput(distDir);
} catch (err) {
  console.error("[clean-pack-output] Failed to clean dist output:", err.message);
  process.exit(1);
}
