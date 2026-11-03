// Activate / deactivate — the per-IDE "make the installed plugin visible
// to the IDE" step, run AFTER `konstera plugin install <slug>` has
// extracted the plugin into ~/.konstera/plugins/<slug>/.
//
// For Claude Code: ~/.konstera/plugins becomes a local marketplace and
// `claude plugin install` adds the plugin from it. Claude Code loads a
// local marketplace's plugin in place, so `konstera plugin install --force`
// reaches the next session with nothing else to run. Going through Claude
// Code's own commands also means a failure here is a real failure: the old
// link into ~/.claude/plugins reported success and loaded nothing.
//
// For future IDEs with different discovery mechanisms, add a case in
// Activate, Deactivate and activationState.

package plugins

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const (
	claudeCodeSlug    = "claude-code"
	claudeMarketplace = "konstera"
	claudePluginName  = "konstera"
	claudePluginID    = claudePluginName + "@" + claudeMarketplace
)

var errClaudeNotFound = errors.New("the claude command is not on PATH")

// runClaude runs the Claude Code CLI and returns its combined output.
// Tests replace it.
var runClaude = func(args ...string) (string, error) {
	path, err := exec.LookPath("claude")
	if err != nil {
		return "", errClaudeNotFound
	}
	out, err := claudeCommand(path, args).CombinedOutput()
	return string(out), err
}

// batchCmdLine is the command line that runs a .cmd or .bat file through
// cmd.exe with every argument intact. Run directly, cmd.exe drops the outer
// quotes when both the file's path and an argument are quoted, so npm's
// claude.cmd under "C:\Users\First Last" failed with "'C:\Users\First' is
// not recognized". /s makes cmd.exe strip only the outer pair added here,
// and /d skips AutoRun commands.
func batchCmdLine(comspec, script string, args []string) string {
	quoted := make([]string, 0, len(args)+1)
	for _, a := range append([]string{script}, args...) {
		quoted = append(quoted, `"`+strings.ReplaceAll(a, `"`, `""`)+`"`)
	}
	return `"` + comspec + `" /d /s /c "` + strings.Join(quoted, " ") + `"`
}

// Activate adds the plugin at ~/.konstera/plugins/<slug> to its IDE.
// Idempotent. apiBaseURL becomes the plugin's API URL.
func Activate(out io.Writer, slug, apiBaseURL string) error {
	if slug == claudeDesktopSlug {
		return activateClaudeDesktop(out, apiBaseURL)
	}
	if slug != claudeCodeSlug {
		return unsupportedSlug("activate", slug)
	}
	source, err := targetPath(slug)
	if err != nil {
		return err
	}
	if _, err := os.Stat(source); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("plugin %q is not installed. Run `konstera plugin install %s` first", slug, slug)
		}
		return fmt.Errorf("checking plugin install: %w", err)
	}

	root := filepath.Dir(source)
	if err := writeMarketplace(root, slug); err != nil {
		return err
	}
	for _, args := range [][]string{
		{"plugin", "marketplace", "add", root},
		{"plugin", "install", claudePluginID, "--config", "base_url=" + apiBaseURL},
	} {
		if err := claudeStep(args, source); err != nil {
			return err
		}
	}
	if err := removeLegacyLink(source); err != nil {
		return err
	}

	fmt.Fprintln(out, "✓ Added the Konstera plugin to Claude Code.")
	fmt.Fprintln(out)
	fmt.Fprintln(out, "Open a new Claude Code session (restart it if it is running), then run /konstera-signin.")
	return nil
}

// Deactivate removes the plugin from its IDE, leaving the install at
// ~/.konstera/plugins/<slug>. Idempotent.
func Deactivate(out io.Writer, slug string) error {
	if slug == claudeDesktopSlug {
		return deactivateClaudeDesktop(out)
	}
	if slug != claudeCodeSlug {
		return unsupportedSlug("deactivate", slug)
	}
	source, err := targetPath(slug)
	if err != nil {
		return err
	}
	if err := removeLegacyLink(source); err != nil {
		return err
	}
	if !claudePluginEnabled() {
		fmt.Fprintf(out, "%s is not active for Claude Code.\n", slug)
		return nil
	}
	for _, args := range [][]string{
		{"plugin", "uninstall", claudePluginID},
		{"plugin", "marketplace", "remove", claudeMarketplace},
	} {
		if err := claudeStep(args, source); err != nil {
			return err
		}
	}
	fmt.Fprintf(out, "✓ Deactivated %s for Claude Code.\n", slug)
	return nil
}

func claudeStep(args []string, source string) error {
	output, err := runClaude(args...)
	if errors.Is(err, errClaudeNotFound) {
		return fmt.Errorf(
			"Claude Code's claude command was not found on PATH. The plugin is at %s. Install Claude Code, then run `konstera plugin activate %s`",
			source, claudeCodeSlug)
	}
	if err != nil {
		return fmt.Errorf("claude %s failed: %w\n%s", strings.Join(args, " "), err, strings.TrimSpace(output))
	}
	return nil
}

func writeMarketplace(root, slug string) error {
	body, err := json.MarshalIndent(map[string]any{
		"name":  claudeMarketplace,
		"owner": map[string]string{"name": "Konstera"},
		"plugins": []map[string]string{{
			"name":        claudePluginName,
			"source":      "./" + slug,
			"description": "Konstera for Claude Code, installed by the Konstera CLI",
		}},
	}, "", "  ")
	if err != nil {
		return err
	}
	dir := filepath.Join(root, ".claude-plugin")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("creating %s: %w", dir, err)
	}
	path := filepath.Join(dir, "marketplace.json")
	if err := os.WriteFile(path, append(body, '\n'), 0o644); err != nil {
		return fmt.Errorf("writing %s: %w", path, err)
	}
	return nil
}

// removeLegacyLink clears the ~/.claude/plugins/<slug> link older CLIs
// created. Anything that does not point at our install is left alone.
func removeLegacyLink(source string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("resolving user home: %w", err)
	}
	link := filepath.Join(home, ".claude", "plugins", filepath.Base(source))
	target, err := os.Readlink(link)
	if err != nil || filepath.Clean(target) != filepath.Clean(source) {
		return nil
	}
	if err := os.Remove(link); err != nil {
		return fmt.Errorf("removing %s: %w", link, err)
	}
	return nil
}

// claudePluginEnabled asks Claude Code rather than inferring from files.
func claudePluginEnabled() bool {
	output, err := runClaude("plugin", "list", "--json")
	if err != nil {
		return false
	}
	var listed []struct {
		ID      string `json:"id"`
		Enabled bool   `json:"enabled"`
	}
	if err := json.Unmarshal([]byte(output), &listed); err != nil {
		return false
	}
	for _, plugin := range listed {
		if plugin.ID == claudePluginID {
			return plugin.Enabled
		}
	}
	return false
}

func unsupportedSlug(verb, slug string) error {
	return fmt.Errorf("konstera plugin %s: no activation handler for slug %q. Supported slugs: %s",
		verb, slug, strings.Join(SupportedActivateSlugs(), ", "))
}

// -- used by cmd/plugin.go to list supported activation targets --------

// SupportedActivateSlugs is the set of slugs this cli knows how to
// activate. Kept here so the command help can enumerate them without
// pulling in cmd/.
func SupportedActivateSlugs() []string {
	return []string{claudeCodeSlug, claudeDesktopSlug}
}
