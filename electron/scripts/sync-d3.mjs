import { cpSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const vendor = join(root, "renderer", "vendor", "d3");
const src = join(root, "node_modules", "d3", "dist", "d3.min.js");
const dest = join(vendor, "d3.min.js");

if (!existsSync(src)) {
  console.error(`missing: ${src} — run npm install in electron/`);
  process.exit(1);
}
mkdirSync(vendor, { recursive: true });
cpSync(src, dest);
console.log(`synced d3 -> ${dest}`);
