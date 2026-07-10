/**
 * Pre-build step for desktop packaging.
 *
 * Builds the frontend (if dist is missing or stale) and copies the Vite build
 * output into desktop/frontend-dist/ so electron-builder bundles it.
 *
 * In production, main.js loads frontend-dist/index.html directly (no dev server).
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const frontendDir = path.join(repoRoot, "frontend");
const frontendDist = path.join(frontendDir, "dist");
const desktopFrontendDist = path.join(__dirname, "frontend-dist");

function run(cmd, cwd, env = {}) {
  console.log(`[prebuild] $ ${cmd}`);
  execSync(cmd, { cwd, stdio: "inherit", env: { ...process.env, ...env } });
}

function needsFrontendBuild() {
  if (!fs.existsSync(frontendDist)) return true;
  if (!fs.existsSync(path.join(frontendDist, "index.html"))) return true;
  const indexHtml = fs.readFileSync(path.join(frontendDist, "index.html"), "utf8");
  // Desktop build uses relative asset paths (base: "./").
  if (!indexHtml.includes("./assets/")) return true;
  if (!fs.existsSync(desktopFrontendDist)) return true;
  return false;
}

function copyDir(src, dst) {
  if (fs.existsSync(dst)) {
    fs.rmSync(dst, { recursive: true, force: true });
  }
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) {
      copyDir(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

try {
  if (needsFrontendBuild()) {
    console.log("[prebuild] Building frontend for desktop (VITE_DESKTOP=1)...");
    run("npm ci --no-audit --no-fund", frontendDir);
    run("npm run build", frontendDir, { VITE_DESKTOP: "1" });
  } else {
    console.log("[prebuild] Frontend dist up-to-date, skipping build.");
  }

  console.log(`[prebuild] Copying ${frontendDist} -> ${desktopFrontendDist}`);
  copyDir(frontendDist, desktopFrontendDist);

  if (process.platform === "win32") {
    console.log("[prebuild] Bundling Windows Python runtime...");
    run("node bundle-python.js", __dirname);
  }

  console.log("[prebuild] Done.");
} catch (err) {
  console.error("[prebuild] Failed:", err.message);
  process.exit(1);
}
