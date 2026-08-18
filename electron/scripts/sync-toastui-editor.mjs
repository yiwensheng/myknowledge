import { cpSync, mkdirSync, existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const vendor = join(root, "renderer", "vendor", "toastui-editor");
const nm = join(root, "node_modules");

const files = [
  ["@toast-ui/editor/dist/toastui-editor.css", "toastui-editor.css"],
  ["@toast-ui/editor/dist/theme/toastui-editor-dark.css", "toastui-editor-dark.css"],
  ["@toast-ui/editor/dist/i18n/zh-cn.js", "i18n-zh-cn.js"],
  ["marked/lib/marked.umd.js", "marked.umd.js"],
];

const allBundleUrl =
  "https://uicdn.toast.com/editor/latest/toastui-editor-all.min.js";
const allBundleDest = join(vendor, "toastui-editor-all.min.js");

mkdirSync(vendor, { recursive: true });
for (const [srcRel, destName] of files) {
  const src = join(nm, ...srcRel.split("/"));
  const dest = join(vendor, destName);
  if (!existsSync(src)) {
    console.error(`missing: ${src}`);
    process.exit(1);
  }
  cpSync(src, dest);
}

const res = await fetch(allBundleUrl);
if (!res.ok) {
  console.error(`failed to fetch ${allBundleUrl}: ${res.status}`);
  process.exit(1);
}
writeFileSync(allBundleDest, Buffer.from(await res.arrayBuffer()));
console.log(`synced ${files.length + 1} files -> ${vendor}`);
