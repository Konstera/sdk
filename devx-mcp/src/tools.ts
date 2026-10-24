import {
  CATALOGUE_VERSION,
  getCapability,
  listCapabilities,
  listCategories,
  searchCapabilities,
  type Capability,
} from "./catalogue.js";

/*
 * The three catalogue read tools exposed over MCP. Each returns a text
 * content block — coding agents (Claude, Cursor, Windsurf) read the text
 * verbatim and quote it back to the user. Shape is optimised for an LLM
 * reader: short preamble line, then one capability per line in a form the
 * model can pattern-match against existing code.
 */

export const TOOL_DEFINITIONS = [
  {
    name: "catalogue_list_capabilities",
    description:
      "List canonical capability keys an agent can call via ctx.capability.*. " +
      "Optionally filter by category (chat, orders, tickets, cloud, ...). " +
      "Use this before suggesting a capability name — the keys returned here are the ones the kernel will actually route.",
    inputSchema: {
      type: "object",
      properties: {
        category: {
          type: "string",
          description: "Optional category filter (e.g. 'orders', 'tickets', 'chat'). Omit to list all categories.",
        },
      },
    },
  },
  {
    name: "catalogue_get_capability",
    description:
      "Fetch a specific capability's full detail: arg schema, response schema, effect (read/write), fanout flag, " +
      "cache TTL, and description. Use after catalogue_list_capabilities to pull the exact shape to code against.",
    inputSchema: {
      type: "object",
      properties: {
        key: {
          type: "string",
          description: "The capability key (e.g. 'orders.lookup_by_email', 'chat.list_new').",
        },
      },
      required: ["key"],
    },
  },
  {
    name: "catalogue_search",
    description:
      "Freetext search across the capability catalogue — matches key, display_name, category, and description. " +
      "Use when the user describes what they want in words ('look up a customer by email', 'post to Slack') " +
      "and you need to resolve that intent to a canonical capability key.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Freetext search terms. Case-insensitive substring match.",
        },
      },
      required: ["query"],
    },
  },
] as const;

type ListInput = { category?: string };
type GetInput = { key: string };
type SearchInput = { query: string };

export function handleListCapabilities(input: ListInput): string {
  const category = input.category;
  const results = listCapabilities(category);
  if (results.length === 0) {
    if (category === undefined) return `No capabilities in catalogue (version ${CATALOGUE_VERSION}).`;
    const known = listCategories();
    return (
      `No capabilities in category '${category}'. ` +
      `Known categories: ${known.join(", ")}.`
    );
  }
  const header = category
    ? `${results.length} capabilities in category '${category}' (catalogue v${CATALOGUE_VERSION}):`
    : `${results.length} capabilities across ${listCategories().length} categories (catalogue v${CATALOGUE_VERSION}):`;
  const lines = results.map((c) => `  ${c.key} — ${c.display_name} (${c.effect})`);
  return [header, "", ...lines].join("\n");
}

export function handleGetCapability(input: GetInput): string {
  const cap = getCapability(input.key);
  if (!cap) {
    return (
      `No capability with key '${input.key}'. ` +
      `Use catalogue_search to find similar keys, or catalogue_list_capabilities to see all.`
    );
  }
  return renderCapabilityDetail(cap);
}

export function handleSearch(input: SearchInput): string {
  const results = searchCapabilities(input.query);
  if (results.length === 0) {
    return (
      `No capabilities matched '${input.query}'. ` +
      `Try catalogue_list_capabilities to see what's available.`
    );
  }
  const header = `${results.length} capabilities matched '${input.query}' (ranked):`;
  const lines = results.slice(0, 20).map((c) =>
    `  ${c.key} — ${c.display_name} (${c.category}, ${c.effect})\n    ${firstSentence(c.description)}`,
  );
  const footer = results.length > 20 ? `\n(${results.length - 20} more; narrow your query to see them)` : "";
  return [header, "", ...lines].join("\n") + footer;
}

function renderCapabilityDetail(cap: Capability): string {
  return [
    `# ${cap.key}`,
    cap.display_name,
    "",
    `**Category:** ${cap.category}`,
    `**Effect:** ${cap.effect}`,
    `**Fanout:** ${cap.fanout ? "yes" : "no"}`,
    `**Cache TTL:** ${cap.cache_ttl_seconds === null ? "none" : `${cap.cache_ttl_seconds}s`}`,
    cap.traits.length > 0 ? `**Traits:** ${cap.traits.join(", ")}` : null,
    "",
    cap.description,
    "",
    "## Request arguments (JSON Schema)",
    "```json",
    JSON.stringify(cap.arg_schema, null, 2),
    "```",
    "",
    "## Response shape (JSON Schema)",
    "```json",
    JSON.stringify(cap.response_schema, null, 2),
    "```",
    "",
    `_Call via_ \`await ctx.capability.call("${cap.key}", {...})\` _from inside your agent's handle()._`,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
}

function firstSentence(text: string): string {
  const match = text.match(/^[^.!?]+[.!?]/);
  return match ? match[0] : text.slice(0, 140);
}
