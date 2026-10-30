// Activate / deactivate — the per-IDE "make the installed plugin visible
// to the IDE" step, run AFTER `konstera plugin install <slug>` has
// extracted the plugin into ~/.konstera/plugins/<slug>/.
//
// For Claude Code: activate symlinks the install dir into ~/.claude/plugins/.
// KNOWN LIMITATION: this does NOT load the plugin. A tester found Claude Code
// 2.1.314 ignores the link; only `claude --plugin-dir <install dir>` or a
// local marketplace loaded it. Install and activate therefore both point at
// --plugin-dir. The command stays available until a working activation
// replaces the link.
//
// For future IDEs with different discovery mechanisms, add a case in
// the dispatch table at the bottom of this file.
//
// We prefer symlinks over copying so the install dir remains the single
// source of truth: upgrades land in ~/.konstera/plugins/<slug>/ via
// `konstera plugin install --force` and the link resolves to the new
// content immediately. No "did I activate the new version?" ambiguity.
//
// Windows caveat: os.Symlink requires either Developer Mode enabled or
// Administrator rights. We fall back to directory junctions via `mklink
// /J` which require neither; junctions resolve dir-only paths and are
// scoped to the same drive, both fine for Konstera's layout.

package plugins

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

// Activate links the plugin at ~/.konstera/plugins/<slug> into the matching
// IDE's plugin directory. Idempotent: a correct symlink/junction already in
// place → logged as already linked, success. Linking is not the same as
// loading; see the limitation at the top of this file.
func Activate(out io.Writer, slug string) error {
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

	dest, hint, err := discoveryPath(slug)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return fmt.Errorf("creating %s: %w", filepath.Dir(dest), err)
	}

	// Inspect the current state at the discovery path. Four cases:
	//   (a) nothing there → create the link
	//   (b) a symlink/junction already pointing at source → nothing to do
	//   (c) a symlink/junction pointing elsewhere → refuse; user must
	//       `konstera plugin deactivate <slug>` first
	//   (d) a plain directory → refuse; user manually copied something
	//       there and we won't clobber their state
	switch state := inspect(dest); state.kind {
	case stateMissing:
		if err := createLink(source, dest); err != nil {
			return fmt.Errorf("linking %s → %s: %w", dest, source, err)
		}
		fmt.Fprintf(out, "✓ Linked %s for %s at %s.\n", slug, hint.ide, dest)
	case stateLinkToUs:
		fmt.Fprintf(out, "✓ %s is already linked for %s at %s.\n", slug, hint.ide, dest)
	case stateLinkElsewhere:
		return fmt.Errorf(
			"%s already has a link at %s pointing at %s. Run `konstera plugin deactivate %s` to remove it, then re-run activate",
			hint.ide, dest, state.target, slug)
	case stateDir, stateFile:
		return fmt.Errorf(
			"%s already has %s at %s. Remove it (manual) and re-run activate; we don't clobber existing content",
			hint.ide, state.kind.describe(), dest)
	}

	if hint.restartNote != "" {
		fmt.Fprintln(out)
		fmt.Fprintln(out, hint.restartNote)
	}
	return nil
}

// Deactivate removes the discovery-dir link we created, leaving the
// installed plugin in place at ~/.konstera/plugins/<slug>. Idempotent.
func Deactivate(out io.Writer, slug string) error {
	source, err := targetPath(slug)
	if err != nil {
		return err
	}
	dest, hint, err := discoveryPath(slug)
	if err != nil {
		return err
	}

	switch state := inspect(dest); state.kind {
	case stateMissing:
		fmt.Fprintf(out, "%s is not active for %s (nothing at %s).\n", slug, hint.ide, dest)
		return nil
	case stateLinkToUs:
		if err := os.Remove(dest); err != nil {
			return fmt.Errorf("removing %s: %w", dest, err)
		}
		fmt.Fprintf(out, "✓ Deactivated %s for %s.\n", slug, hint.ide)
	case stateLinkElsewhere:
		return fmt.Errorf(
			"%s at %s links to %s, not to our install at %s. Deactivate refuses to remove something we didn't create — remove it manually",
			hint.ide, dest, state.target, source)
	case stateDir, stateFile:
		return fmt.Errorf(
			"%s at %s is %s, not one of our links. Deactivate refuses to clobber it; remove it manually if you intend to",
			hint.ide, dest, state.kind.describe())
	}
	return nil
}

// -- link-state inspection ---------------------------------------------

type linkStateKind int

const (
	stateMissing linkStateKind = iota
	stateLinkToUs
	stateLinkElsewhere
	stateDir
	stateFile
)

func (k linkStateKind) describe() string {
	switch k {
	case stateDir:
		return "a plain directory"
	case stateFile:
		return "a regular file"
	case stateLinkElsewhere:
		return "a symlink"
	case stateLinkToUs:
		return "our symlink"
	default:
		return "nothing"
	}
}

type linkState struct {
	kind   linkStateKind
	target string
}

func inspect(path string) linkState {
	// Lstat does NOT follow symlinks — critical here because we need to
	// know "is this a link" before deciding "where does it point."
	fi, err := os.Lstat(path)
	if err != nil {
		return linkState{kind: stateMissing}
	}
	source := ourSourceFor(path)
	if fi.Mode()&os.ModeSymlink != 0 {
		target, err := os.Readlink(path)
		if err != nil {
			return linkState{kind: stateLinkElsewhere, target: "<unreadable>"}
		}
		if filepath.Clean(target) == filepath.Clean(source) {
			return linkState{kind: stateLinkToUs, target: target}
		}
		return linkState{kind: stateLinkElsewhere, target: target}
	}
	// On Windows, directory junctions aren't flagged ModeSymlink; since
	// Go 1.23 Lstat reports them as ModeIrregular rather than ModeDir.
	// Readlink resolves their target.
	if runtime.GOOS == "windows" && (fi.IsDir() || fi.Mode()&os.ModeIrregular != 0) {
		if target, err := os.Readlink(path); err == nil && target != "" {
			if filepath.Clean(target) == filepath.Clean(source) {
				return linkState{kind: stateLinkToUs, target: target}
			}
			return linkState{kind: stateLinkElsewhere, target: target}
		}
	}
	if fi.IsDir() {
		return linkState{kind: stateDir}
	}
	return linkState{kind: stateFile}
}

// ourSourceFor returns what the install path for a plugin at this
// discovery path should be — used by inspect to decide "is this link
// ours or someone else's".
func ourSourceFor(discoveryPath string) string {
	slug := filepath.Base(discoveryPath)
	source, err := targetPath(slug)
	if err != nil {
		return ""
	}
	return source
}

// -- link creation (symlink + Windows junction fallback) ----------------

func createLink(source, dest string) error {
	// Try symlink first on every OS. Fast path on macOS/Linux and on
	// Windows machines with Developer Mode or admin.
	err := os.Symlink(source, dest)
	if err == nil {
		return nil
	}
	if runtime.GOOS != "windows" {
		return err
	}
	// Windows symlink failed — most likely "A required privilege is not
	// held by the client" (ERROR_PRIVILEGE_NOT_HELD, 1314). Fall back to
	// a directory junction via mklink /J which doesn't require admin.
	// mklink is a cmd.exe builtin, not a .exe, so it has to run via cmd.
	msg := err.Error()
	if strings.Contains(msg, "privilege") || strings.Contains(msg, "1314") {
		cmd := exec.Command("cmd", "/C", "mklink", "/J", dest, source)
		if out, err2 := cmd.CombinedOutput(); err2 != nil {
			return fmt.Errorf("symlink refused and mklink /J fallback failed: %s", strings.TrimSpace(string(out)))
		}
		return nil
	}
	return err
}

// -- per-IDE discovery path dispatch -----------------------------------

type discoveryHint struct {
	ide         string
	restartNote string
}

// discoveryPath returns where a given plugin slug is linked into for its
// target IDE, plus a human description + post-activate hint.
func discoveryPath(slug string) (string, discoveryHint, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", discoveryHint{}, fmt.Errorf("resolving user home: %w", err)
	}

	switch slug {
	case "claude-code":
		// The link lands in ~/.claude/plugins/ on every OS. Claude Code does
		// not load it (see the limitation at the top of this file), so the
		// post-activate note gives the command that does.
		path := filepath.Join(home, ".claude", "plugins", slug)
		source, err := targetPath(slug)
		if err != nil {
			return "", discoveryHint{}, err
		}
		return path, discoveryHint{
			ide: "Claude Code",
			restartNote: claudeCodeLoadSteps(
				"Note: this link does not currently load the plugin; Claude Code (tested on 2.1.314) ignores it.\n"+
					"To load the plugin, start Claude Code with (the flag applies to that session only):",
				source),
		}, nil
	default:
		return "", discoveryHint{}, fmt.Errorf(
			"konstera plugin activate: no activation handler for slug %q. Supported slugs: claude-code", slug)
	}
}

// -- used by cmd/plugin.go to list supported activation targets --------

// SupportedActivateSlugs is the set of slugs this cli knows how to
// activate. Kept here so the command help can enumerate them without
// pulling in cmd/.
func SupportedActivateSlugs() []string {
	return []string{"claude-code"}
}
