// Move CJS build to .cjs and ESM build to .mjs so the "exports" field in
// package.json resolves correctly across both module systems. TypeScript
// emits .js regardless of module format; renaming post-build is the
// standard dual-build fix.

import { readdirSync, renameSync, copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join, extname } from "node:path";

const DIST = "dist";
const CJS = join(DIST, "cjs");
const ESM = join(DIST, "esm");

function renameAllInDir(dir, fromExt, toExt) {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      renameAllInDir(full, fromExt, toExt);
    } else if (extname(entry.name) === fromExt) {
      const target = full.slice(0, -fromExt.length) + toExt;
      renameSync(full, target);
    }
  }
}

// Rename CJS .js -> .cjs
renameAllInDir(CJS, ".js", ".cjs");
renameAllInDir(CJS, ".js.map", ".cjs.map");

// Rename ESM .js -> .mjs
renameAllInDir(ESM, ".js", ".mjs");
renameAllInDir(ESM, ".js.map", ".mjs.map");

// Hoist from dist/cjs/* and dist/esm/* up to dist/* so the exports field is clean.
function copyUp(sourceDir, destDir) {
  if (!existsSync(sourceDir)) return;
  mkdirSync(destDir, { recursive: true });
  for (const entry of readdirSync(sourceDir, { withFileTypes: true })) {
    const srcPath = join(sourceDir, entry.name);
    const dstPath = join(destDir, entry.name);
    if (entry.isDirectory()) {
      copyUp(srcPath, dstPath);
    } else {
      copyFileSync(srcPath, dstPath);
    }
  }
}

copyUp(CJS, DIST);
copyUp(ESM, DIST);

// Clean up intermediate dirs
if (existsSync(CJS)) rmSync(CJS, { recursive: true });
if (existsSync(ESM)) rmSync(ESM, { recursive: true });

console.log("dist/ structure finalised — index.cjs, index.mjs, index.d.ts hoisted to top.");
