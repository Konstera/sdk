package plugins

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func useDesktopConfig(t *testing.T, initial string) string {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "Claude")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "claude_desktop_config.json")
	if initial != "" {
		if err := os.WriteFile(path, []byte(initial), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	oldPath, oldExe, oldRunning := ClaudeDesktopConfigPath, executable, claudeDesktopRunning
	ClaudeDesktopConfigPath = func() (string, error) { return path, nil }
	executable = func() (string, error) { return `C:\Tools\konstera.exe`, nil }
	claudeDesktopRunning = func() (bool, error) { return false, nil }
	t.Cleanup(func() { ClaudeDesktopConfigPath, executable, claudeDesktopRunning = oldPath, oldExe, oldRunning })
	return path
}

func readConfig(t *testing.T, path string) map[string]any {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var cfg map[string]any
	if err := json.Unmarshal(raw, &cfg); err != nil {
		t.Fatalf("config is not JSON: %v\n%s", err, raw)
	}
	return cfg
}

func TestActivateClaudeDesktopKeepsOtherSettings(t *testing.T) {
	path := useDesktopConfig(t, `{
  "mcpServers": {
    "other": {"command": "npx", "args": ["x"]},
    "konstera-devx": {"url": "https://api.konstera.ai/mcp/devx", "headers": {"Authorization": "Bearer old"}}
  },
  "preferences": {"coworkWebSearchEnabled": true, "big": 12345678901234567890}
}`)
	var out bytes.Buffer
	if err := Activate(&out, claudeDesktopSlug, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	cfg := readConfig(t, path)
	servers := cfg["mcpServers"].(map[string]any)
	if _, ok := servers["other"]; !ok {
		t.Error("another MCP server was removed")
	}
	if _, ok := servers["konstera-devx"]; ok {
		t.Error("the stale URL entry was kept")
	}
	entry := servers["konstera"].(map[string]any)
	if entry["command"] != `C:\Tools\konstera.exe` {
		t.Errorf("command = %v", entry["command"])
	}
	args, _ := json.Marshal(entry["args"])
	if string(args) != `["mcp","--client","claude-desktop","--api-url","https://api.konstera.ai"]` {
		t.Errorf("args = %s", args)
	}
	raw, _ := os.ReadFile(path)
	if !strings.Contains(string(raw), "12345678901234567890") || cfg["preferences"].(map[string]any)["coworkWebSearchEnabled"] != true {
		t.Errorf("preferences changed:\n%s", raw)
	}
	if !strings.Contains(out.String(), "Open Claude Desktop") {
		t.Errorf("output = %q", out.String())
	}

	// Idempotent, then deactivate removes only ours.
	if err := Activate(&out, claudeDesktopSlug, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	if err := Deactivate(&out, claudeDesktopSlug); err != nil {
		t.Fatal(err)
	}
	servers = readConfig(t, path)["mcpServers"].(map[string]any)
	if _, ok := servers["konstera"]; ok {
		t.Error("deactivate left the entry")
	}
	if _, ok := servers["other"]; !ok {
		t.Error("deactivate removed another server")
	}
}

func TestActivateClaudeDesktopKeepsUserEntryUnderLegacyKey(t *testing.T) {
	path := useDesktopConfig(t, `{"mcpServers": {"konstera-devx": {"command": "node", "args": ["mine.js"]}}}`)
	if err := Activate(&bytes.Buffer{}, claudeDesktopSlug, "http://localhost:4500"); err != nil {
		t.Fatal(err)
	}
	if _, ok := readConfig(t, path)["mcpServers"].(map[string]any)["konstera-devx"]; !ok {
		t.Error("a command entry the user made under konstera-devx was removed")
	}
}

func TestActivateClaudeDesktopRefusesBrokenConfig(t *testing.T) {
	path := useDesktopConfig(t, `{"mcpServers": `)
	err := Activate(&bytes.Buffer{}, claudeDesktopSlug, "http://localhost:4500")
	if err == nil || !strings.Contains(err.Error(), "left alone") {
		t.Fatalf("err = %v", err)
	}
	if raw, _ := os.ReadFile(path); string(raw) != `{"mcpServers": ` {
		t.Error("a broken config was overwritten")
	}
}

func TestActivateClaudeDesktopCreatesMissingFile(t *testing.T) {
	path := useDesktopConfig(t, "")
	if err := Activate(&bytes.Buffer{}, claudeDesktopSlug, "http://localhost:4500"); err != nil {
		t.Fatal(err)
	}
	if _, ok := readConfig(t, path)["mcpServers"].(map[string]any)["konstera"]; !ok {
		t.Error("entry not written")
	}
}

func installExtension(t *testing.T, configPath, folder, name string) {
	t.Helper()
	dir := filepath.Join(filepath.Dir(configPath), "Claude Extensions", folder)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), []byte(`{"manifest_version":"0.3","name":"`+name+`"}`), 0o644); err != nil {
		t.Fatal(err)
	}
}

// With the .mcpb extension installed, activate must not add a second server:
// Claude Desktop would start Konstera twice, and on Windows the extra process
// locks ~/.konstera/bin/konstera.exe so the installer can't update it.
func TestActivateClaudeDesktopWithExtensionRemovesOlderEntry(t *testing.T) {
	path := useDesktopConfig(t, `{"mcpServers":{"konstera":{"command":"C:/old/konstera.exe","args":["mcp"]},"other":{"command":"x"}},"theme":"dark"}`)
	installExtension(t, path, "local.mcpb.konstera.konstera", "konstera")

	var out bytes.Buffer
	if err := activateClaudeDesktop(&out, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	cfg := readConfig(t, path)
	servers := cfg["mcpServers"].(map[string]any)
	if _, ok := servers["konstera"]; ok {
		t.Fatalf("konstera entry kept next to the extension: %v", servers)
	}
	if _, ok := servers["other"]; !ok || cfg["theme"] != "dark" {
		t.Fatalf("other settings lost: %v", cfg)
	}
	if !strings.Contains(out.String(), "already installed") || !strings.Contains(out.String(), "Removed the older Konstera entry") {
		t.Fatalf("unexpected output:\n%s", out.String())
	}
}

func TestActivateClaudeDesktopWithExtensionAddsNothing(t *testing.T) {
	path := useDesktopConfig(t, `{"mcpServers":{}}`)
	installExtension(t, path, "some-other-folder-name", "konstera")

	var out bytes.Buffer
	if err := activateClaudeDesktop(&out, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	if servers := readConfig(t, path)["mcpServers"].(map[string]any); len(servers) != 0 {
		t.Fatalf("expected no servers, got %v", servers)
	}
	if strings.Contains(out.String(), "Removed") {
		t.Fatalf("claimed a removal with nothing to remove:\n%s", out.String())
	}
}

// Another extension (different manifest name) doesn't count.
func TestActivateClaudeDesktopIgnoresOtherExtensions(t *testing.T) {
	path := useDesktopConfig(t, `{"mcpServers":{}}`)
	installExtension(t, path, "local.mcpb.someone.konstera-like", "not-konstera")

	if err := activateClaudeDesktop(&bytes.Buffer{}, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	if _, ok := readConfig(t, path)["mcpServers"].(map[string]any)["konstera"]; !ok {
		t.Fatal("expected the konstera entry when no Konstera extension is installed")
	}
}
