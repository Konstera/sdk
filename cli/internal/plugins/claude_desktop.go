package plugins

// Claude Desktop has no Claude Code plugin runtime, so "activating" it
// means adding `konstera mcp` (this CLI, as a local MCP server) to Claude
// Desktop's own config file. Nothing is downloaded: the CLI is the
// integration. Sign-in happens inside Claude Desktop (konstera_sign_in).

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
)

const (
	claudeDesktopSlug = "claude-desktop"
	// desktopServerKey is the mcpServers key `konstera mcp` is added under.
	desktopServerKey = "konstera"
	// legacyFanoutKey is the URL + fixed-token entry older `konstera login`
	// runs wrote. Claude Desktop cannot use it and its token expires within
	// the hour, so activation removes it.
	legacyFanoutKey = "konstera-devx"
)

// executable is the path Claude Desktop runs. Tests replace it.
var executable = func() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	if resolved, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolved
	}
	return exe, nil
}

// ClaudeDesktopConfigPath is claude_desktop_config.json for this OS.
var ClaudeDesktopConfigPath = func() (string, error) {
	switch runtime.GOOS {
	case "windows":
		appData := os.Getenv("APPDATA")
		if appData == "" {
			return "", errors.New("APPDATA is not set")
		}
		return filepath.Join(appData, "Claude", "claude_desktop_config.json"), nil
	case "darwin":
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json"), nil
	default:
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, ".config", "Claude", "claude_desktop_config.json"), nil
	}
}

func activateClaudeDesktop(out io.Writer, apiBaseURL string) error {
	path, err := ClaudeDesktopConfigPath()
	if err != nil {
		return err
	}
	if _, err := os.Stat(filepath.Dir(path)); errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("Claude Desktop does not look installed (no %s). Install it, open it once, then run `konstera plugin activate %s`",
			filepath.Dir(path), claudeDesktopSlug)
	}
	exe, err := executable()
	if err != nil {
		return fmt.Errorf("finding the konstera executable: %w", err)
	}
	err = editDesktopConfig(path, func(servers map[string]any) {
		servers[desktopServerKey] = map[string]any{
			"command": exe,
			"args":    []string{"mcp", "--client", claudeDesktopSlug, "--api-url", apiBaseURL},
		}
		if isLegacyFanoutEntry(servers[legacyFanoutKey]) {
			delete(servers, legacyFanoutKey)
		}
	})
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "✓ Added Konstera to Claude Desktop (%s).\n", path)
	fmt.Fprintln(out)
	fmt.Fprintln(out, "Quit Claude Desktop completely (also from the system tray) and open it again.")
	fmt.Fprintln(out, "Then ask Claude to \"sign in to Konstera\"; approve the request in your browser.")
	return nil
}

func deactivateClaudeDesktop(out io.Writer) error {
	path, err := ClaudeDesktopConfigPath()
	if err != nil {
		return err
	}
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		fmt.Fprintf(out, "%s is not active for Claude Desktop.\n", claudeDesktopSlug)
		return nil
	}
	removed := false
	err = editDesktopConfig(path, func(servers map[string]any) {
		if _, ok := servers[desktopServerKey]; ok {
			delete(servers, desktopServerKey)
			removed = true
		}
	})
	if err != nil {
		return err
	}
	if !removed {
		fmt.Fprintf(out, "%s is not active for Claude Desktop.\n", claudeDesktopSlug)
		return nil
	}
	fmt.Fprintln(out, "✓ Removed Konstera from Claude Desktop. Restart Claude Desktop to apply.")
	fmt.Fprintln(out, "  To also end the pairing, ask Claude to sign out of Konstera before restarting.")
	return nil
}

func isLegacyFanoutEntry(v any) bool {
	entry, ok := v.(map[string]any)
	if !ok {
		return false
	}
	_, hasURL := entry["url"]
	_, hasCommand := entry["command"]
	return hasURL && !hasCommand
}

// editDesktopConfig changes only mcpServers; every other setting Claude
// Desktop keeps in the file is written back as it was.
func editDesktopConfig(path string, edit func(servers map[string]any)) error {
	cfg, err := readJSONObject(path)
	if errors.Is(err, os.ErrNotExist) {
		cfg = map[string]any{}
	} else if err != nil {
		return err
	}
	servers, _ := cfg["mcpServers"].(map[string]any)
	if servers == nil {
		servers = map[string]any{}
	}
	edit(servers)
	cfg["mcpServers"] = servers

	body, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".*.tmp")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	if _, err := tmp.Write(append(body, '\n')); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("writing %s: %w", path, err)
	}
	return nil
}

func readJSONObject(path string) (map[string]any, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	cfg := map[string]any{}
	if len(raw) == 0 {
		return cfg, nil
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber() // keep numbers exactly as Claude Desktop wrote them
	if err := dec.Decode(&cfg); err != nil {
		return nil, fmt.Errorf("%s is not valid JSON, so it was left alone: %w", path, err)
	}
	return cfg, nil
}
