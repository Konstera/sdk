package plugins

import (
	"bytes"
	"errors"
	"os"
	"strings"
	"testing"
)

func TestIsClaudeDesktopExe(t *testing.T) {
	cases := map[string]bool{
		`C:\Users\me\AppData\Local\AnthropicClaude\app-4.4212.0\claude.exe`: true,
		`c:\users\me\appdata\local\anthropicclaude\app-1.0.0\CLAUDE.EXE`:    true,
		`C:/Users/me/AppData/Local/AnthropicClaude/app-1.0.0/claude.exe`:    true,
		`C:\Users\me\.local\bin\claude.exe`:                                 false, // Claude Code
		`C:\Users\me\AppData\Roaming\npm\node_modules\claude.exe`:           false,
		`C:\Users\me\AppData\Local\AnthropicClaude\Update.exe`:              false,
		``: false,
	}
	for path, want := range cases {
		if got := isClaudeDesktopExe(path); got != want {
			t.Errorf("isClaudeDesktopExe(%q) = %v, want %v", path, got, want)
		}
	}
}

func TestIsClaudeDesktopMacCommand(t *testing.T) {
	cases := map[string]bool{
		"812 /Applications/Claude.app/Contents/MacOS/Claude":                                                         true,
		"913 /Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper --type=gpu": false,
		"77 /opt/homebrew/bin/claude": false,
	}
	for cmd, want := range cases {
		if got := isClaudeDesktopMacCommand(cmd); got != want {
			t.Errorf("isClaudeDesktopMacCommand(%q) = %v, want %v", cmd, got, want)
		}
	}
}

func TestActivateClaudeDesktopRefusesWhileRunning(t *testing.T) {
	const initial = `{"mcpServers": {"other": {"command": "x"}}}`
	path := useDesktopConfig(t, initial)
	claudeDesktopRunning = func() (bool, error) { return true, nil }

	err := Activate(&bytes.Buffer{}, claudeDesktopSlug, "https://api.konstera.ai")
	if err == nil {
		t.Fatal("activate went ahead while Claude Desktop was running")
	}
	for _, want := range []string{"Claude Desktop is running", "Quit Claude Desktop", "claude_desktop_config.json"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error does not mention %q:\n%v", want, err)
		}
	}
	if raw, _ := os.ReadFile(path); string(raw) != initial {
		t.Errorf("config was changed:\n%s", raw)
	}
}

func TestDeactivateClaudeDesktopRefusesWhileRunning(t *testing.T) {
	const initial = `{"mcpServers": {"konstera": {"command": "konstera", "args": ["mcp"]}}}`
	path := useDesktopConfig(t, initial)
	claudeDesktopRunning = func() (bool, error) { return true, nil }

	if err := Deactivate(&bytes.Buffer{}, claudeDesktopSlug); err == nil || !strings.Contains(err.Error(), "Claude Desktop is running") {
		t.Fatalf("err = %v", err)
	}
	if raw, _ := os.ReadFile(path); string(raw) != initial {
		t.Errorf("config was changed:\n%s", raw)
	}
}

func TestDeactivateClaudeDesktopNothingToRemoveWhileRunning(t *testing.T) {
	useDesktopConfig(t, `{"mcpServers": {"other": {"command": "x"}}}`)
	claudeDesktopRunning = func() (bool, error) { return true, nil }

	var out bytes.Buffer
	if err := Deactivate(&out, claudeDesktopSlug); err != nil {
		t.Fatalf("nothing to remove, but err = %v", err)
	}
	if !strings.Contains(out.String(), "not active") {
		t.Errorf("output = %q", out.String())
	}
}

func TestActivateClaudeDesktopWarnsWhenCheckFails(t *testing.T) {
	path := useDesktopConfig(t, "")
	claudeDesktopRunning = func() (bool, error) { return false, errors.New("access denied") }

	var out bytes.Buffer
	if err := Activate(&out, claudeDesktopSlug, "https://api.konstera.ai"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "Could not check whether Claude Desktop is running") {
		t.Errorf("no warning in output: %q", out.String())
	}
	if _, ok := readConfig(t, path)["mcpServers"].(map[string]any)["konstera"]; !ok {
		t.Error("entry not written")
	}
}

// The real detector must run without error on this OS. Whether Claude
// Desktop is running depends on the machine, so only the error is checked.
func TestDetectClaudeDesktopRuns(t *testing.T) {
	if _, err := detectClaudeDesktop(); err != nil {
		t.Fatalf("detectClaudeDesktop: %v", err)
	}
}
