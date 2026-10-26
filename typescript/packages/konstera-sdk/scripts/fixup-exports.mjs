// Move CJS build to .cjs and ESM build to .mjs so the "exports" field in
// package.json resolves correctly across both module systems. TypeScript
// emits .js regardless of module format; renaming post-build is the
// standard dual-build fix.

import { readdirSync, readFileSync, writeFileSync, renameSync, copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const DIST = "dist";
const CJS = join(DIST, "cjs");
const ESM = join(DIST, "esm");

// Relative specifiers ("./agent.js", "../services/cost.js") inside the emitted
// code still say .js after the rename, so they must be rewritten too or every
// import of a sibling module fails at runtime.
const RELATIVE_JS = /(["'])(\.{1,2}\/[^"']+?)\.js\1/g;

function renameAllInDir(dir, toExt) {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      renameAllInDir(full, toExt);
    } else if (entry.name.endsWith(".js.map")) {
      renameSync(full, full.slice(0, -".js.map".length) + `${toExt}.map`);
    } else if (entry.name.endsWith(".js")) {
      const code = readFileSync(full, "utf8")
        .replace(RELATIVE_JS, `$1$2${toExt}$1`)
        .replace(/(\/\/# sourceMappingURL=.+?)\.js\.map/, `$1${toExt}.map`);
      writeFileSync(full.slice(0, -".js".length) + toExt, code);
      rmSync(full);
    }
  }
}

// Rename CJS .js -> .cjs
renameAllInDir(CJS, ".cjs");

// Rename ESM .js -> .mjs
renameAllInDir(ESM, ".mjs");

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
