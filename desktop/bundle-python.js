/**
 * Bundle Windows embeddable CPython + backend dependencies for desktop packaging.
 *
 * Output: desktop/bundled-python/ (packed as extraResources/python/)
 * Skips on non-Windows platforms.
 */

const fs = require("fs");
const path = require("path");
const https = require("https");
const crypto = require("crypto");
const { execFileSync, spawnSync } = require("child_process");
const { createWriteStream } = require("fs");

const PYTHON_VERSION = "3.12.8";
const ARCH = process.arch === "x64" ? "amd64" : "win32";
const REPO_ROOT = path.resolve(__dirname, "..");
const OUTPUT_DIR = path.join(__dirname, "bundled-python");
const CACHE_DIR = path.join(__dirname, ".cache");
const REQUIREMENTS_LOCK = path.join(REPO_ROOT, "backend", "requirements.lock");
const LOCK_DIGEST_FILE = path.join(OUTPUT_DIR, ".requirements-lock.sha256");
const ZIP_NAME = `python-${PYTHON_VERSION}-embed-${ARCH}.zip`;
const ZIP_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/${ZIP_NAME}`;

function download(url, dest) {
  return new Promise((resolve, reject) => {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    const file = createWriteStream(dest);
    https
      .get(url, (res) => {
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          file.close();
          fs.unlinkSync(dest);
          download(res.headers.location, dest).then(resolve).catch(reject);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed: ${res.statusCode} ${url}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => file.close(() => resolve(dest)));
      })
      .on("error", reject);
  });
}

function run(cmd, args, options = {}) {
  console.log(`[bundle-python] $ ${cmd} ${args.join(" ")}`);
  const result = spawnSync(cmd, args, { stdio: "inherit", ...options });
  if (result.status !== 0) {
    throw new Error(`Command failed: ${cmd} ${args.join(" ")}`);
  }
}

async function main() {
  if (process.platform !== "win32") {
    console.log("[bundle-python] Skipping — Windows-only bundling step.");
    return;
  }

  const pythonExe = path.join(OUTPUT_DIR, "python.exe");
  const lockDigest = crypto
    .createHash("sha256")
    .update(fs.readFileSync(REQUIREMENTS_LOCK))
    .digest("hex");
  if (fs.existsSync(pythonExe)) {
    const cachedDigest = fs.existsSync(LOCK_DIGEST_FILE)
      ? fs.readFileSync(LOCK_DIGEST_FILE, "utf8").trim()
      : "";
    const probe = spawnSync(pythonExe, ["-c", "import uvicorn, chromadb"], {
      cwd: path.join(REPO_ROOT, "backend"),
      stdio: "pipe",
    });
    if (probe.status === 0 && cachedDigest === lockDigest) {
      console.log("[bundle-python] Existing bundle looks healthy, skipping rebuild.");
      return;
    }
    console.log("[bundle-python] Existing bundle incomplete or stale, rebuilding...");
    fs.rmSync(OUTPUT_DIR, { recursive: true, force: true });
  }

  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const zipPath = path.join(CACHE_DIR, ZIP_NAME);
  if (!fs.existsSync(zipPath)) {
    console.log(`[bundle-python] Downloading ${ZIP_URL}`);
    await download(ZIP_URL, zipPath);
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  run("powershell", [
    "-NoProfile",
    "-Command",
    `Expand-Archive -Path '${zipPath.replace(/'/g, "''")}' -DestinationPath '${OUTPUT_DIR.replace(/'/g, "''")}' -Force`,
  ]);

  const pthFiles = fs.readdirSync(OUTPUT_DIR).filter((f) => f.endsWith("._pth"));
  if (pthFiles.length === 0) {
    throw new Error("Could not find embeddable python *._pth file");
  }
  const pthPath = path.join(OUTPUT_DIR, pthFiles[0]);
  const pthBase = pthFiles[0].replace(/^\./, "").replace(/\._pth$/, "");
  fs.mkdirSync(path.join(OUTPUT_DIR, "Lib", "site-packages"), { recursive: true });
  // Embeddable builds ship with `# import site` commented out; pip needs site + site-packages.
  fs.writeFileSync(
    pthPath,
    `${pthBase}.zip\n.\nLib\\site-packages\nimport site\n`,
    "utf8",
  );

  const getPipPath = path.join(CACHE_DIR, "get-pip.py");
  if (!fs.existsSync(getPipPath)) {
    await download("https://bootstrap.pypa.io/get-pip.py", getPipPath);
  }

  run(pythonExe, [getPipPath, "--no-warn-script-location"], { cwd: OUTPUT_DIR });
  run(pythonExe, [
    "-m",
    "pip",
    "install",
    "--no-warn-script-location",
    "--require-hashes",
    "-r",
    REQUIREMENTS_LOCK,
  ], { cwd: OUTPUT_DIR });

  const verify = spawnSync(
    pythonExe,
    [
      "-c",
      `import sys; sys.path.insert(0, r'${path.join(REPO_ROOT, "backend").replace(/\\/g, "\\\\")}'); import uvicorn, chromadb, app.main`,
    ],
    { cwd: path.join(REPO_ROOT, "backend"), stdio: "inherit" },
  );
  if (verify.status !== 0) {
    throw new Error("Bundled python failed import verification");
  }
  fs.writeFileSync(LOCK_DIGEST_FILE, `${lockDigest}\n`, "utf8");

  console.log("[bundle-python] Bundle ready at", OUTPUT_DIR);
}

main().catch((err) => {
  console.error("[bundle-python] Failed:", err.message);
  process.exit(1);
});
