import catalogue from "./data/capability-catalog.json" with { type: "json" };

/*
 * Loads the vendored capability catalogue + indexes it for fast lookup
 * by key, by category, and freetext search. The data file at
 * src/data/capability-catalog.json is copied from sdk/schemas/ by the
 * prebuild script (scripts/copy-catalogue.mjs).
 */

export type Capability = {
  readonly key: string;
  readonly display_name: string;
  readonly category: string;
  readonly description: string;
  readonly effect: string;
  readonly fanout: boolean;
  readonly traits: readonly string[];
  readonly cache_ttl_seconds: number | null;
  readonly arg_schema: unknown;
  readonly response_schema: unknown;
};

type CatalogueFile = {
  readonly version: string | number;
  readonly description?: string;
  readonly capabilities: readonly Capability[];
};

const data = catalogue as unknown as CatalogueFile;

export const CATALOGUE_VERSION: string = String(data.version);

export const CAPABILITIES: readonly Capability[] = data.capabilities;

const BY_KEY = new Map<string, Capability>(CAPABILITIES.map((c) => [c.key, c]));

export function getCapability(key: string): Capability | undefined {
  return BY_KEY.get(key);
}

export function listCapabilities(category?: string): Capability[] {
  if (category === undefined) return CAPABILITIES.slice().sort((a, b) => a.key.localeCompare(b.key));
  const needle = category.toLowerCase();
  return CAPABILITIES.filter((c) => c.category.toLowerCase() === needle).sort((a, b) =>
    a.key.localeCompare(b.key),
  );
}

export function listCategories(): string[] {
  return Array.from(new Set(CAPABILITIES.map((c) => c.category))).sort();
}

/**
 * Freetext match across key, display_name, description, and category.
 * Case-insensitive substring; results ranked key-first (strongest signal
 * that the user remembers roughly what they want to call), then
 * display_name hits, then description hits.
 */
export function searchCapabilities(query: string): Capability[] {
  const q = query.trim().toLowerCase();
  if (q.length === 0) return [];

  const hits: Array<{ cap: Capability; rank: number }> = [];
  for (const cap of CAPABILITIES) {
    let rank = 0;
    if (cap.key.toLowerCase().includes(q)) rank += 100;
    if (cap.display_name.toLowerCase().includes(q)) rank += 50;
    if (cap.category.toLowerCase().includes(q)) rank += 20;
    if (cap.description.toLowerCase().includes(q)) rank += 10;
    if (rank > 0) hits.push({ cap, rank });
  }
  hits.sort((a, b) => b.rank - a.rank || a.cap.key.localeCompare(b.cap.key));
  return hits.map((h) => h.cap);
}
