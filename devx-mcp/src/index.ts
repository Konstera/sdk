import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  TOOL_DEFINITIONS,
  handleGetCapability,
  handleListCapabilities,
  handleSearch,
} from "./tools.js";

/*
 * Konstera DevX MCP server — v1 scope (ADR-013 catalogue read tools).
 *
 * Starts an MCP server over stdio and exposes three tools agent-authoring
 * environments (Claude Desktop, Cursor, Windsurf, Claude Code) can call:
 *
 *   catalogue_list_capabilities(category?)
 *   catalogue_get_capability(key)
 *   catalogue_search(query)
 *
 * The data behind these tools is a vendored snapshot of the capability
 * catalogue — the same file the Python / TypeScript / .NET SDKs ship.
 * Freshness: the snapshot copies at build time via prebuild
 * (scripts/copy-catalogue.mjs).
 */

export async function createServer(): Promise<Server> {
  const server = new Server(
    {
      name: "konstera-devx-mcp",
      version: "0.1.0",
    },
    {
      capabilities: {
        tools: {},
      },
    },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOL_DEFINITIONS.map((t) => ({ ...t })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const name = request.params.name;
    const args = (request.params.arguments ?? {}) as Record<string, unknown>;

    switch (name) {
      case "catalogue_list_capabilities": {
        const category = typeof args["category"] === "string" ? args["category"] : undefined;
        const text = handleListCapabilities(category === undefined ? {} : { category });
        return { content: [{ type: "text", text }] };
      }
      case "catalogue_get_capability": {
        if (typeof args["key"] !== "string") {
          return {
            content: [{ type: "text", text: "catalogue_get_capability requires a string 'key' argument." }],
            isError: true,
          };
        }
        const text = handleGetCapability({ key: args["key"] });
        return { content: [{ type: "text", text }] };
      }
      case "catalogue_search": {
        if (typeof args["query"] !== "string") {
          return {
            content: [{ type: "text", text: "catalogue_search requires a string 'query' argument." }],
            isError: true,
          };
        }
        const text = handleSearch({ query: args["query"] });
        return { content: [{ type: "text", text }] };
      }
      default:
        return {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }
  });

  return server;
}

export async function main(): Promise<void> {
  const server = await createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
