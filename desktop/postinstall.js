/**
 * Cross-platform postinstall: generate icon.png when Python is available.
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const iconPath = path.join(__dirname, "icon.png");
const needsIcon =
  !fs.existsSync(iconPath) ||
  (() => {
    try {
      const buf = fs.readFileSync(iconPath);
      // PNG IHDR width/height at bytes 16-23
      if (buf.length < 24 || buf.toString("ascii", 12, 16) !== "IHDR") return true;
      const width = buf.readUInt32BE(16);
      const height = buf.readUInt32BE(20);
      return width < 256 || height < 256;
    } catch {
      return true;
    }
  })();

if (!needsIcon) {
  process.exit(0);
}

const candidates =
  process.platform === "win32"
    ? [["py", ["-3.12", "generate_icon.py"]], ["python", ["generate_icon.py"]]]
    : [["python3", ["generate_icon.py"]], ["python", ["generate_icon.py"]]];

for (const [cmd, args] of candidates) {
  const result = spawnSync(cmd, args, { cwd: __dirname, stdio: "inherit" });
  if (result.status === 0) {
    process.exit(0);
  }
}

console.warn("[postinstall] Skipping icon generation — Python not found (optional).");
