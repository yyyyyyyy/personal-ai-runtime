const fs = require("fs");
const path = require("path");
const os = require("os");

const base = require("./package.json").build;
const bundledPython = path.join(__dirname, "bundled-python", "python.exe");
const outputDir =
  process.env.DESKTOP_BUILD_OUTPUT ||
  path.join(os.homedir(), ".cache", "personal-ai-runtime-desktop", "dist");

const extraResources = [...base.extraResources.filter((item) => item.to !== "python")];
if (fs.existsSync(bundledPython)) {
  extraResources.push({
    from: "bundled-python",
    to: "python",
    filter: ["**/*"],
  });
}

module.exports = {
  ...base,
  directories: {
    ...base.directories,
    output: outputDir,
  },
  win: {
    ...base.win,
    signAndEditExecutable: false,
  },
  extraResources,
};
