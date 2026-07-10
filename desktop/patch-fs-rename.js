/**
 * Retry fs.promises.rename on Windows EPERM races during electron unpack.
 */
const fsp = require("fs/promises");

const originalRename = fsp.rename.bind(fsp);

fsp.rename = async function patchedRename(oldPath, newPath) {
  const isUnpackRename =
    typeof oldPath === "string" &&
    typeof newPath === "string" &&
    oldPath.includes("win-unpacked.tmp") &&
    newPath.includes("win-unpacked");

  const attempts = isUnpackRename ? 30 : 1;
  let lastError;
  for (let i = 0; i < attempts; i++) {
    try {
      return await originalRename(oldPath, newPath);
    } catch (err) {
      lastError = err;
      if (!isUnpackRename || (err.code !== "EPERM" && err.code !== "EACCES")) {
        throw err;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw lastError;
};
