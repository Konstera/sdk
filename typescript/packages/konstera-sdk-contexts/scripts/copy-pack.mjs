// Post-build step: copies the raw pack JSON into dist/ so consumers can
// import "konstera-sdk-contexts/pack.json" for metadata-driven UIs.
// The source of truth is sdk/schemas/standard-context-pack-v1.json.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..", "..", "..");
const src = resolve(repoRoot, "schemas", "standard-context-pack-v1.json");
const dst = resolve(here, "..", "dist", "standard-context-pack-v1.json");

mkdirSync(dirname(dst), { recursive: true });
copyFileSync(src, dst);
console.log(`copied pack → ${dst}`);
