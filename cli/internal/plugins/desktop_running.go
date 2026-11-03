package plugins

import (
	"fmt"
	"path/filepath"
	"runtime"
	"strings"
)

// Claude Desktop keeps claude_desktop_config.json in memory and writes it
// back when it quits, so an edit made while it runs is lost. Activation
// therefore refuses while it is running.

// claudeDesktopRunning reports whether Claude Desktop is running. Tests
// replace it.
var claudeDesktopRunning = detectClaudeDesktop

// isClaudeDesktopExe matches the Windows Claude Desktop executable
// (%LOCALAPPDATA%\AnthropicClaude\app-<version>\claude.exe). Claude Code's
// own claude.exe lives elsewhere and must not match.
func isClaudeDesktopExe(path string) bool {
	p := strings.ToLower(strings.ReplaceAll(path, "/", `\`))
	return strings.HasSuffix(p, `\claude.exe`) && strings.Contains(p, `\anthropicclaude\`)
}

// isClaudeDesktopMacCommand matches the main macOS Claude Desktop process.
// Its helpers run from Claude.app/Contents/Frameworks/..., so they do not
// match; Claude Code ("claude" from a bin directory) does not either.
func isClaudeDesktopMacCommand(command string) bool {
	return strings.Contains(command, "Claude.app/Contents/MacOS/Claude")
}

// checkClaudeDesktopClosed returns an error telling the user to quit
// Claude Desktop when it is running. If the check itself fails it warns
// and lets the edit go ahead: refusing then would block every user whose
// process list cannot be read.
func checkClaudeDesktopClosed(warn func(string), configPath string) error {
	running, err := claudeDesktopRunning()
	if err != nil {
		warn(fmt.Sprintf("Could not check whether Claude Desktop is running (%v). If it is, quit it first, or it will undo this change.", err))
		return nil
	}
	if !running {
		return nil
	}
	return fmt.Errorf(`Claude Desktop is running. It rewrites %s when it quits, which would undo this change.

Quit Claude Desktop completely, then run this command again:
  %s

Or install the Konstera extension instead, which needs no config edit:
  https://konstera.ai/docs/cli#claude-desktop`, filepath.Base(configPath), quitClaudeDesktopHint())
}

func quitClaudeDesktopHint() string {
	switch runtime.GOOS {
	case "windows":
		return `File > Exit in Claude Desktop (or right-click its tray icon > Quit), or in PowerShell:
  Get-Process claude | Where-Object Path -like '*\AnthropicClaude\*' | Stop-Process`
	case "darwin":
		return `Claude > Quit Claude (Cmd+Q), or in a terminal:
  osascript -e 'quit app "Claude"'`
	default:
		return "Quit Claude Desktop."
	}
}
