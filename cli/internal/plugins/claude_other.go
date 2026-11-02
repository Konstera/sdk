//go:build !windows

package plugins

import "os/exec"

func claudeCommand(path string, args []string) *exec.Cmd {
	return exec.Command(path, args...)
}
