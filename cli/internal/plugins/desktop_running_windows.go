//go:build windows

package plugins

import (
	"errors"
	"syscall"
	"unsafe"
)

const processQueryLimitedInformation = 0x1000

var procQueryFullProcessImageNameW = syscall.NewLazyDLL("kernel32.dll").NewProc("QueryFullProcessImageNameW")

// detectClaudeDesktop walks the process list for a claude.exe under
// AnthropicClaude. The image name alone is not enough: Claude Code's CLI
// is also claude.exe.
func detectClaudeDesktop() (bool, error) {
	snap, err := syscall.CreateToolhelp32Snapshot(syscall.TH32CS_SNAPPROCESS, 0)
	if err != nil {
		return false, err
	}
	defer syscall.CloseHandle(snap)

	var entry syscall.ProcessEntry32
	entry.Size = uint32(unsafe.Sizeof(entry))
	for err = syscall.Process32First(snap, &entry); err == nil; err = syscall.Process32Next(snap, &entry) {
		name := syscall.UTF16ToString(entry.ExeFile[:])
		if !equalFoldASCII(name, "claude.exe") {
			continue
		}
		if path, ok := processImagePath(entry.ProcessID); ok && isClaudeDesktopExe(path) {
			return true, nil
		}
	}
	if errors.Is(err, syscall.ERROR_NO_MORE_FILES) {
		return false, nil
	}
	return false, err
}

func processImagePath(pid uint32) (string, bool) {
	h, err := syscall.OpenProcess(processQueryLimitedInformation, false, pid)
	if err != nil {
		return "", false
	}
	defer syscall.CloseHandle(h)
	buf := make([]uint16, 1024)
	size := uint32(len(buf))
	r, _, _ := procQueryFullProcessImageNameW.Call(uintptr(h), 0, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&size)))
	if r == 0 {
		return "", false
	}
	return syscall.UTF16ToString(buf[:size]), true
}

func equalFoldASCII(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := 0; i < len(a); i++ {
		ca, cb := a[i], b[i]
		if 'A' <= ca && ca <= 'Z' {
			ca += 'a' - 'A'
		}
		if 'A' <= cb && cb <= 'Z' {
			cb += 'a' - 'A'
		}
		if ca != cb {
			return false
		}
	}
	return true
}
