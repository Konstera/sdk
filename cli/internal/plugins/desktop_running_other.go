//go:build !windows

package plugins

import (
	"errors"
	"os/exec"
	"runtime"
	"strings"
)

// detectClaudeDesktop looks for the Claude app's main process on macOS.
// There is no Claude Desktop for Linux, so elsewhere it reports false.
func detectClaudeDesktop() (bool, error) {
	if runtime.GOOS != "darwin" {
		return false, nil
	}
	out, err := exec.Command("pgrep", "-fl", "Claude.app/Contents/MacOS/Claude").Output()
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) && exitErr.ExitCode() == 1 {
		return false, nil // pgrep: no match
	}
	if err != nil {
		return false, err
	}
	for _, line := range strings.Split(string(out), "\n") {
		if isClaudeDesktopMacCommand(line) {
			return true, nil
		}
	}
	return false, nil
}
