/**
 * Shared helpers for cleaning electron-builder output on Windows.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const STALE_DIR_NAMES = ["win-unpacked", "win-unpacked.tmp", "mac", "linux-unpacked"];

function killPackagedDesktopProcesses() {
  if (process.platform !== "win32") return;
  for (const image of ["Personal AI Runtime.exe", "electron.exe"]) {
    spawnSync("taskkill", ["/F", "/IM", image, "/T"], { stdio: "ignore" });
  }
}

function removeDirResilient(target, logPrefix = "[clean-pack-output]") {
  if (!fs.existsSync(target)) return;

  try {
    fs.rmSync(target, { recursive: true, force: true, maxRetries: 12, retryDelay: 500 });
    console.log(`${logPrefix} removed ${path.basename(target)}`);
    return;
  } catch (err) {
    if (err.code !== "EPERM" && err.code !== "EBUSY" && err.code !== "EACCES") {
      throw err;
    }
  }

  const stale = `${target}.stale-${Date.now()}`;
  try {
    fs.renameSync(target, stale);
    console.warn(
      `${logPrefix} could not delete ${path.basename(target)}; renamed to ${path.basename(stale)}`,
    );
  } catch {
    throw new Error(
      `Cannot remove ${target}. Close Personal AI Runtime / Electron and any File Explorer ` +
        "windows showing that folder, then retry.",
    );
  }
}

function cleanDistOutput(distDir, logPrefix = "[clean-pack-output]") {
  if (!fs.existsSync(distDir)) return;
  killPackagedDesktopProcesses();
  for (const name of STALE_DIR_NAMES) {
    removeDirResilient(path.join(distDir, name), logPrefix);
  }
}

module.exports = {
  STALE_DIR_NAMES,
  killPackagedDesktopProcesses,
  removeDirResilient,
  cleanDistOutput,
};
