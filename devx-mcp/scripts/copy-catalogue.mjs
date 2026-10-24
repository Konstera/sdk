#!/usr/bin/env node
/*
 * Build-time copy of sdk/schemas/capability-catalog.json into
 * src/data/capability-catalog.json so the compiled package can bundle it
 * without reaching into the sibling schemas/ folder at runtime.
 *
 * The SDK repo's capability-catalog.json is the single source of truth for
 * every language SDK; this script keeps devx-mcp in lockstep with that
 * canonical file. If the schema drifts across SDK + devx-mcp, this
 * mechanism surfaces it on the next build.
 */
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SOURCE = resolve(__dirname, "..", "..", "schemas", "capability-catalog.json");
const TARGET = resolve(__dirname, "..", "src", "data", "capability-catalog.json");

await mkdir(dirname(TARGET), { recursive: true });
await copyFile(SOURCE, TARGET);
console.log(`[copy-catalogue] ${SOURCE} -> ${TARGET}`);
