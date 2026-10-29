package login

import (
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Test that writeOne creates the config file, inserts the konstera-devx
// entry, and preserves existing non-Konstera entries.
func TestWriteOne_InsertsKonsteraEntry_PreservesOthers(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cursor-mcp.json")

	// Seed a pre-existing config with a non-Konstera entry.
	existing := map[string]any{
		"mcpServers": map[string]any{
			"my-other-tool": map[string]any{"command": "/usr/local/bin/my-tool"},
		},
	}
	raw, _ := json.MarshalIndent(existing, "", "  ")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatalf("seed: %v", err)
	}

	entry := map[string]any{"url": "http://localhost:4500/mcp/devx", "headers": map[string]string{"Authorization": "Bearer T"}}
	target := MCPConfigTarget{Tool: "Cursor", Path: path, MCPKey: "mcpServers"}
	if err := writeOne(target, entry, false); err != nil {
		t.Fatalf("writeOne: %v", err)
	}

	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read back: %v", err)
	}
	var out map[string]any
	if err := json.Unmarshal(body, &out); err != nil {
		t.Fatalf("parse written: %v", err)
	}
	servers, ok := out["mcpServers"].(map[string]any)
	if !ok {
		t.Fatalf("mcpServers missing or wrong shape: %v", out)
	}
	if _, ok := servers["my-other-tool"]; !ok {
		t.Fatalf("pre-existing entry was deleted — must preserve non-Konstera entries")
	}
	if _, ok := servers[konsteraServerKey]; !ok {
		t.Fatalf("konstera-devx entry missing")
	}
}

// Test that writeOne creates a brand-new config file when none exists.
func TestWriteOne_CreatesFile_WhenMissing(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "subdir/mcp.json")   // includes a missing parent dir

	entry := map[string]any{"url": "http://localhost:4500/mcp/devx", "headers": map[string]string{"Authorization": "Bearer T"}}
	target := MCPConfigTarget{Tool: "Cursor", Path: path, MCPKey: "mcpServers"}
	if err := writeOne(target, entry, false); err != nil {
		t.Fatalf("writeOne: %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("file was not created: %v", err)
	}
}

// Test that a re-pair updates the token in place rather than appending.
func TestWriteOne_RepairUpdatesEntry(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mcp.json")

	target := MCPConfigTarget{Tool: "Cursor", Path: path, MCPKey: "mcpServers"}

	first := map[string]any{"url": "http://localhost:4500/mcp/devx", "headers": map[string]string{"Authorization": "Bearer OLD"}}
	if err := writeOne(target, first, false); err != nil {
		t.Fatalf("first write: %v", err)
	}
	second := map[string]any{"url": "http://localhost:4500/mcp/devx", "headers": map[string]string{"Authorization": "Bearer NEW"}}
	if err := writeOne(target, second, false); err != nil {
		t.Fatalf("second write: %v", err)
	}
	body, _ := os.ReadFile(path)
	if !strings.Contains(string(body), "Bearer NEW") {
		t.Fatalf("expected updated token in file:\n%s", body)
	}
	if strings.Contains(string(body), "Bearer OLD") {
		t.Fatalf("stale token still present:\n%s", body)
	}
	// Only one occurrence of the key.
	if strings.Count(string(body), konsteraServerKey) != 1 {
		t.Fatalf("expected exactly one konstera-devx key, got %d:\n%s", strings.Count(string(body), konsteraServerKey), body)
	}
}

// Test that corrupt existing configs surface a clear parse error.
func TestWriteOne_CorruptExisting_ReturnsError(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mcp.json")
	if err := os.WriteFile(path, []byte("not json at all"), 0o600); err != nil {
		t.Fatalf("seed: %v", err)
	}
	target := MCPConfigTarget{Tool: "Cursor", Path: path, MCPKey: "mcpServers"}
	err := writeOne(target, map[string]any{"url": "x"}, false)
	if err == nil {
		t.Fatalf("expected parse error on corrupt existing file")
	}
	if !strings.Contains(err.Error(), "parse existing") {
		t.Fatalf("expected 'parse existing' in error, got: %v", err)
	}
}

// Test that WriteMCPConfigs skips tools whose parent dirs do not exist
// and succeeds for ones that do.
func TestWriteMCPConfigs_SkipsMissing_WritesPresent(t *testing.T) {
	// Point HOME at a temp dir, create only Cursor's parent dir.
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
	// APPDATA is Windows-only; harmless to set on POSIX.
	t.Setenv("APPDATA", home)

	if err := os.MkdirAll(filepath.Join(home, ".cursor"), 0o700); err != nil {
		t.Fatalf("mk cursor dir: %v", err)
	}

	c := &Credentials{
		APIBaseURL:  "http://localhost:4500",
		AccessToken: "test-token",
	}
	res, err := WriteMCPConfigs(c, false, io.Discard)
	if err != nil {
		t.Fatalf("fan-out: %v", err)
	}
	wrote := strings.Join(res.Wrote, ",")
	if !strings.Contains(wrote, "Cursor") {
		t.Fatalf("expected Cursor to be written, got %v", res.Wrote)
	}
	// Other tools whose dirs we did not create must be in Skipped.
	if len(res.Skipped) == 0 {
		t.Fatalf("expected some tools to be skipped; wrote=%v", res.Wrote)
	}
}
