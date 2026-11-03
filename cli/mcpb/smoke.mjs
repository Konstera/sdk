// Smoke-tests a packed Konstera extension the way Claude Desktop runs it.
//
//   node cli/mcpb/smoke.mjs <bundle.mcpb> <expected-version>
//
// Unpacks the bundle with the mcpb library (the code Claude Desktop uses to
// load bundles), resolves command/args/env for this OS with
// getMcpConfigForManifest, starts the server, and speaks MCP over stdio:
// initialize, notifications/initialized, tools/list. Passes when the server
// reports the expected version and offers konstera_sign_in.
//
// The server gets a throwaway KONSTERA_HOME, so it never sees (or renews)
// a real sign-in, and KONSTERA_NO_BROWSER=1. It makes no network calls when
// signed out.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, sep } from "node:path";
import { getMcpConfigForManifest, unpackExtension } from "@anthropic-ai/mcpb";

const [bundle, wantVersion] = process.argv.slice(2);
if (!bundle || !wantVersion) {
  console.error("usage: node smoke.mjs <bundle.mcpb> <expected-version>");
  process.exit(2);
}

const root = mkdtempSync(join(tmpdir(), "konstera-mcpb-"));
const extDir = join(root, "ext");
const home = join(root, "home");
let child;

function fail(msg) {
  console.error(`FAIL ${bundle}: ${msg}`);
  child?.kill();
  rmSync(root, { recursive: true, force: true });
  process.exit(1);
}

if (!(await unpackExtension({ mcpbPath: bundle, outputDir: extDir, silent: true }))) {
  fail("unpack failed");
}
const manifest = JSON.parse(readFileSync(join(extDir, "manifest.json"), "utf8"));
if (manifest.version !== wantVersion) fail(`manifest version ${manifest.version}, want ${wantVersion}`);
if (!manifest.compatibility?.platforms?.includes(process.platform)) {
  fail(`bundle is for ${manifest.compatibility?.platforms}, this is ${process.platform}`);
}

const config = await getMcpConfigForManifest({
  manifest,
  extensionPath: extDir,
  systemDirs: { HOME: home, DESKTOP: home, DOCUMENTS: home, DOWNLOADS: home },
  userConfig: {},
  pathSeparator: sep,
});
if (!config) fail("no MCP config for this platform");
console.log(`command: ${config.command}`);
console.log(`args:    ${JSON.stringify(config.args)}`);

child = spawn(config.command, config.args ?? [], {
  env: { ...process.env, ...(config.env ?? {}), KONSTERA_HOME: home, KONSTERA_NO_BROWSER: "1" },
  stdio: ["pipe", "pipe", "pipe"],
});
child.on("error", (err) => fail(`could not start: ${err.message}`));
child.stderr.on("data", (d) => process.stderr.write(`[server] ${d}`));

const pending = new Map();
let buf = "";
child.stdout.on("data", (d) => {
  buf += d;
  let nl;
  while ((nl = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      fail(`stdout is not JSON-RPC: ${line.slice(0, 200)}`);
    }
    pending.get(msg.id)?.(msg);
  }
});

let nextId = 1;
function request(method, params) {
  const id = nextId++;
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${method}: no reply in 15s`)), 15000);
    pending.set(id, (msg) => {
      clearTimeout(timer);
      msg.error ? reject(new Error(`${method}: ${JSON.stringify(msg.error)}`)) : resolve(msg.result);
    });
  });
}

try {
  const init = await request("initialize", {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "claude-ai", version: "smoke" },
  });
  console.log(`initialize: ${JSON.stringify(init.serverInfo)} protocol ${init.protocolVersion}`);
  if (init.serverInfo?.name !== "konstera") fail(`serverInfo.name = ${init.serverInfo?.name}`);
  if (init.serverInfo?.version !== wantVersion) fail(`serverInfo.version = ${init.serverInfo?.version}, want ${wantVersion}`);
  child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

  const { tools } = await request("tools/list", {});
  const names = tools.map((t) => t.name);
  console.log(`tools/list: ${names.join(", ")}`);
  if (!names.includes("konstera_sign_in")) fail("konstera_sign_in missing from tools/list");
} catch (err) {
  fail(err.message);
}

child.stdin.end();
child.kill();
rmSync(root, { recursive: true, force: true });
console.log(`PASS ${bundle}`);
