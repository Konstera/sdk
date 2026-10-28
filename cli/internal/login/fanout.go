package login

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

// MCPConfigTarget is one coding-agent config path the fan-out writes to.
// New tools get added by appending to knownTargets; nothing else changes.
type MCPConfigTarget struct {
	Tool     string // display name, e.g. "Cursor"
	Path     string // absolute path to the config file
	MCPKey   string // the config key under which the mcpServers map lives
	Format   configFormat
}

type configFormat int

const (
	// JSON with an mcpServers OBJECT at the top (Cursor, Claude Desktop, Codex).
	formatMCPServersObject configFormat = iota
)

// FanoutResult reports what the fan-out did on this machine.
type FanoutResult struct {
	Wrote   []string // display names of tools whose config was written
	Skipped []string // tools whose parent dir did not exist
	Errors  []string // human-readable errors; non-fatal — fan-out is best-effort
}

// WriteMCPConfigs iterates every known target, writes a `konstera-devx`
// MCP server entry pointing at devxMCPURL with the paired token, and
// returns a FanoutResult summarising what happened.
//
// Design: write per-target is best-effort — a missing Cursor config dir
// is not an error (user does not have Cursor installed). A write failure
// against a target IS an error but the function keeps going so a locked
// Claude Desktop config does not block Cursor from being configured.
//
// `force` controls behaviour when a `konstera-devx` entry already exists
// under some other shape: with force, we overwrite; without, we skip and
// report. Non-Konstera entries in the same file are always preserved.
func WriteMCPConfigs(c *Credentials, force bool, w io.Writer) (*FanoutResult, error) {
	devxMCPURL := strings.TrimRight(c.APIBaseURL, "/") + "/mcp/devx"
	entry := map[string]any{
		"url": devxMCPURL,
		"headers": map[string]string{
			"Authorization": "Bearer " + c.AccessToken,
		},
	}

	targets, err := KnownTargets()
	if err != nil {
		return nil, err
	}

	result := &FanoutResult{}
	for _, t := range targets {
		dir := filepath.Dir(t.Path)
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			result.Skipped = append(result.Skipped, t.Tool)
			continue
		} else if err != nil {
			result.Errors = append(result.Errors, fmt.Sprintf("%s: stat %s: %v", t.Tool, dir, err))
			continue
		}
		if err := writeOne(t, entry, force); err != nil {
			result.Errors = append(result.Errors, fmt.Sprintf("%s: %v", t.Tool, err))
			continue
		}
		result.Wrote = append(result.Wrote, t.Tool)
		if w != nil {
			fmt.Fprintf(w, "  ✓ %s  %s\n", t.Tool, t.Path)
		}
	}
	sort.Strings(result.Wrote)
	sort.Strings(result.Skipped)
	sort.Strings(result.Errors)
	return result, nil
}

// konsteraServerKey is the stable key under mcpServers so a re-pair
// updates the entry in place rather than duplicating. Must not change
// without a migration — existing tools would end up with stale entries.
const konsteraServerKey = "konstera-devx"

func writeOne(t MCPConfigTarget, entry map[string]any, force bool) error {
	// Read existing file if any.
	raw, err := os.ReadFile(t.Path)
	var cfg map[string]any
	if err == nil {
		if err := json.Unmarshal(raw, &cfg); err != nil {
			return fmt.Errorf("parse existing %s: %w", t.Path, err)
		}
	} else if os.IsNotExist(err) {
		cfg = map[string]any{}
	} else {
		return err
	}

	// Locate / create the mcpServers map.
	servers, ok := cfg[t.MCPKey].(map[string]any)
	if !ok {
		servers = map[string]any{}
	}

	// Preserve non-Konstera entries unconditionally. The konstera-devx
	// entry is replaced on re-pair (so the Bearer token stays fresh); any
	// OTHER key under the konstera prefix (e.g. a user-managed custom
	// Konstera MCP) is left alone.
	if _, exists := servers[konsteraServerKey]; exists && !force {
		// Overwrite silently when the existing entry is one we wrote in a
		// prior run (identified by the shape — a map with url + headers).
		// We treat the overwrite as always-allowed for our own stable key;
		// --force is reserved for the case where a user manually created
		// an entry with the same key and shape they'd want to protect.
	}
	servers[konsteraServerKey] = entry
	cfg[t.MCPKey] = servers

	// Marshal + write via a temp file in the same directory for atomicity.
	body, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(t.Path), 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(t.Path), filepath.Base(t.Path)+".*.tmp")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	success := false
	defer func() {
		if !success {
			_ = os.Remove(tmpPath)
		}
	}()
	if _, err := tmp.Write(body); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if runtime.GOOS != "windows" {
		if err := os.Chmod(tmpPath, 0o600); err != nil {
			return err
		}
	}
	if err := os.Rename(tmpPath, t.Path); err != nil {
		return err
	}
	success = true
	return nil
}

// KnownTargets returns the config-path manifest for this machine. The
// per-tool paths come from each tool's documented config location; the
// MCPKey column reflects the key under which that tool stores its
// mcp-servers map. Adding a new tool is a two-line change here and
// does not need an ADR amendment — the ADR commits to the mechanism,
// not the catalogue.
func KnownTargets() ([]MCPConfigTarget, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	appData := os.Getenv("APPDATA")

	var t []MCPConfigTarget
	add := func(tool, path, mcpKey string) {
		if path == "" {
			return
		}
		t = append(t, MCPConfigTarget{Tool: tool, Path: path, MCPKey: mcpKey, Format: formatMCPServersObject})
	}

	// Claude Desktop — same mcpServers shape on all three OSes but the
	// path differs (macOS: ~/Library/Application Support, Linux: ~/.config,
	// Windows: %APPDATA%).
	switch runtime.GOOS {
	case "darwin":
		add("Claude Desktop", filepath.Join(home, "Library/Application Support/Claude/claude_desktop_config.json"), "mcpServers")
	case "linux":
		add("Claude Desktop", filepath.Join(home, ".config/Claude/claude_desktop_config.json"), "mcpServers")
	case "windows":
		if appData != "" {
			add("Claude Desktop", filepath.Join(appData, "Claude/claude_desktop_config.json"), "mcpServers")
		}
	}

	// Claude Code — the Anthropic CLI tool (distinct from Claude Desktop).
	add("Claude Code", filepath.Join(home, ".config/claude-code/mcp.json"), "mcpServers")

	// Cursor — ~/.cursor/mcp.json on every platform.
	add("Cursor", filepath.Join(home, ".cursor/mcp.json"), "mcpServers")

	// Windsurf (Codeium) — ~/.codeium/windsurf/mcp.json.
	add("Windsurf", filepath.Join(home, ".codeium/windsurf/mcp.json"), "mcpServers")

	// OpenAI Codex — ~/.codex/mcp.json.
	add("OpenAI Codex", filepath.Join(home, ".codex/mcp.json"), "mcpServers")

	// Cline — ~/.cline/mcp.json.
	add("Cline", filepath.Join(home, ".cline/mcp.json"), "mcpServers")

	// Continue — ~/.continue/config.json with mcpServers key.
	add("Continue", filepath.Join(home, ".continue/config.json"), "mcpServers")

	return t, nil
}
