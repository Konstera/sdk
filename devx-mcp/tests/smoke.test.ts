import { describe, expect, test } from "vitest";
import {
  CATALOGUE_VERSION,
  CAPABILITIES,
  getCapability,
  listCapabilities,
  listCategories,
  searchCapabilities,
} from "../src/catalogue.js";
import {
  TOOL_DEFINITIONS,
  handleGetCapability,
  handleListCapabilities,
  handleSearch,
} from "../src/tools.js";

/*
 * Smoke tests that cover the shape of each tool handler. These run against
 * the vendored capability catalogue, so if someone pushes a bad catalogue
 * the tests catch it before the devx-mcp package publishes.
 */

describe("catalogue", () => {
  test("vendored catalogue is non-empty with a version", () => {
    expect(CATALOGUE_VERSION).toMatch(/\S/);
    expect(CAPABILITIES.length).toBeGreaterThan(0);
  });

  test("every capability has a key, display_name, category, and effect", () => {
    for (const cap of CAPABILITIES) {
      expect(cap.key).toMatch(/\S/);
      expect(cap.display_name).toMatch(/\S/);
      expect(cap.category).toMatch(/\S/);
      expect(cap.effect).toMatch(/\S/);
    }
  });

  test("getCapability resolves a known key + returns undefined for unknown", () => {
    const first = CAPABILITIES[0]!;
    expect(getCapability(first.key)?.key).toBe(first.key);
    expect(getCapability("absolutely.not.a.real.capability")).toBeUndefined();
  });

  test("listCapabilities filters by category", () => {
    const categories = listCategories();
    expect(categories.length).toBeGreaterThan(0);
    const sampled = categories[0]!;
    const filtered = listCapabilities(sampled);
    expect(filtered.length).toBeGreaterThan(0);
    expect(filtered.every((c) => c.category === sampled)).toBe(true);
  });

  test("searchCapabilities ranks key-match over description-match", () => {
    const first = CAPABILITIES[0]!;
    const keyFragment = first.key.split(/[._]/)[0] ?? first.key.slice(0, 4);
    const hits = searchCapabilities(keyFragment);
    expect(hits.length).toBeGreaterThan(0);
    // The first hit should contain the key fragment somewhere in its key
    expect(hits[0]!.key.toLowerCase()).toContain(keyFragment.toLowerCase());
  });

  test("searchCapabilities returns empty on empty query", () => {
    expect(searchCapabilities("")).toEqual([]);
    expect(searchCapabilities("   ")).toEqual([]);
  });
});

describe("tool definitions", () => {
  test("three tools exposed, each with name + description + inputSchema", () => {
    expect(TOOL_DEFINITIONS).toHaveLength(3);
    for (const t of TOOL_DEFINITIONS) {
      expect(t.name).toMatch(/^catalogue_/);
      expect(t.description.length).toBeGreaterThan(40);
      expect(t.inputSchema.type).toBe("object");
    }
  });
});

describe("tool handlers", () => {
  test("handleListCapabilities (no filter) returns a formatted list", () => {
    const text = handleListCapabilities({});
    expect(text).toContain("capabilities");
    expect(text).toContain("catalogue v");
    expect(text.split("\n").length).toBeGreaterThan(CAPABILITIES.length);
  });

  test("handleListCapabilities with unknown category points at the known set", () => {
    const text = handleListCapabilities({ category: "absolutely-not-a-real-category" });
    expect(text).toContain("Known categories");
  });

  test("handleGetCapability renders a markdown-ish detail block for a known key", () => {
    const first = CAPABILITIES[0]!;
    const text = handleGetCapability({ key: first.key });
    expect(text).toContain(`# ${first.key}`);
    expect(text).toContain("## Request arguments");
    expect(text).toContain("## Response shape");
    expect(text).toContain(`ctx.capability.call("${first.key}"`);
  });

  test("handleGetCapability points at search when key is unknown", () => {
    const text = handleGetCapability({ key: "nothing.like.this" });
    expect(text).toContain("No capability with key");
    expect(text).toContain("catalogue_search");
  });

  test("handleSearch returns ranked hits for a common fragment", () => {
    const first = CAPABILITIES[0]!;
    const fragment = first.category;
    const text = handleSearch({ query: fragment });
    expect(text).toContain("matched");
    expect(text.toLowerCase()).toContain(fragment.toLowerCase());
  });

  test("handleSearch degrades gracefully with no hits", () => {
    const text = handleSearch({ query: "zzzzz-nothing-matches-this-xxxx" });
    expect(text).toContain("No capabilities matched");
  });
});
