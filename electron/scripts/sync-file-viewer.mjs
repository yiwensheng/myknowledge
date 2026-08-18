/** Copy @file-viewer/web-full dist into renderer/vendor for offline preview. */
import { cpSync, existsSync, rmSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "@file-viewer", "web-full", "dist");
const dest = join(root, "renderer", "vendor", "file-viewer");

if (!existsSync(src)) {
  console.error("[sync-file-viewer] 未找到 @file-viewer/web-full，请先运行 npm install");
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log("[sync-file-viewer] 已同步到 renderer/vendor/file-viewer");
