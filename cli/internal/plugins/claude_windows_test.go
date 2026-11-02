//go:build windows

package plugins

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// npm installs Claude Code as claude.cmd under the user's profile. With a
// space in both the script's path and an argument, cmd.exe used to split
// the path and never run the script.
func TestClaudeCommandRunsCmdWithSpacesInPathAndArgs(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "First Last")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(dir, "claude.cmd")
	if err := os.WriteFile(script, []byte("@echo ARGS: %*\r\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	arg := filepath.Join(dir, ".konstera", "plugins")

	out, err := claudeCommand(script, []string{"plugin", "marketplace", "add", arg}).CombinedOutput()
	if err != nil {
		t.Fatalf("claude.cmd did not run: %v\n%s", err, out)
	}
	if want := `ARGS: "plugin" "marketplace" "add" "` + arg + `"`; !strings.Contains(string(out), want) {
		t.Fatalf("output %q, want it to contain %q", out, want)
	}
}
