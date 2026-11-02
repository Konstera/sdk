//go:build windows

package plugins

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
)

// claudeCommand runs claude.exe directly and npm's claude.cmd through
// cmd.exe with quoting that survives spaces (see batchCmdLine).
func claudeCommand(path string, args []string) *exec.Cmd {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".cmd", ".bat":
	default:
		return exec.Command(path, args...)
	}
	comspec := os.Getenv("ComSpec")
	if comspec == "" {
		comspec = filepath.Join(os.Getenv("SystemRoot"), "System32", "cmd.exe")
	}
	cmd := exec.Command(comspec)
	cmd.SysProcAttr = &syscall.SysProcAttr{CmdLine: batchCmdLine(comspec, path, args)}
	return cmd
}
