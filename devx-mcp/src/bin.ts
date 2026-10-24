#!/usr/bin/env node
import { main } from "./index.js";

main().catch((err: unknown) => {
  // eslint-disable-next-line no-console
  console.error("[konstera-devx-mcp] fatal:", err);
  process.exit(1);
});
