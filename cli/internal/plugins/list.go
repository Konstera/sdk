package plugins

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"
)

const (
	versionUnknown = "unknown"

	activatedYes = "yes"
	activatedNo  = "no"
	activatedNA  = "n/a" // the slug has no activation handler
)

// InstalledPlugin is one row of `konstera plugin list`.
type InstalledPlugin struct {
	Slug      string
	Version   string // versionUnknown when the plugin doesn't record one
	Activated string // activatedYes, activatedNo or activatedNA
}

// Installed reads ~/.konstera/plugins/ and returns its plugins sorted by
// slug. A missing plugins directory means nothing is installed, not an error.
func Installed() ([]InstalledPlugin, error) {
	dir, err := pluginsDir()
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(dir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", dir, err)
	}

	var installed []InstalledPlugin
	for _, entry := range entries {
		if !entry.IsDir() || isTransientDir(entry.Name()) {
			continue
		}
		slug := entry.Name()
		version, ok := readInstalledVersion(filepath.Join(dir, slug))
		if !ok {
			version = versionUnknown
		}
		installed = append(installed, InstalledPlugin{
			Slug:      slug,
			Version:   version,
			Activated: activationState(slug),
		})
	}
	return installed, nil
}

// isTransientDir matches the directories extractAtomic leaves behind if a
// run is interrupted: .plugin-<slug>-stage-* staging dirs and
// <slug>.old-<nanos> backups. Neither is an installed plugin.
func isTransientDir(name string) bool {
	return strings.HasPrefix(name, ".") || strings.Contains(name, ".old-")
}

func activationState(slug string) string {
	if slug != claudeCodeSlug {
		return activatedNA
	}
	if claudePluginEnabled() {
		return activatedYes
	}
	return activatedNo
}

// List prints the installed plugins as a table.
func List(out io.Writer) error {
	installed, err := Installed()
	if err != nil {
		return err
	}
	if len(installed) == 0 {
		fmt.Fprintln(out, "No plugins installed. Run `konstera plugin install claude-code` to install one.")
		return nil
	}

	tw := tabwriter.NewWriter(out, 0, 0, 2, ' ', 0)
	fmt.Fprintln(tw, "SLUG\tVERSION\tACTIVATED")
	for _, p := range installed {
		fmt.Fprintf(tw, "%s\t%s\t%s\n", p.Slug, p.Version, p.Activated)
	}
	if err := tw.Flush(); err != nil {
		return err
	}

	for _, p := range installed {
		if p.Activated == activatedNo {
			fmt.Fprintf(out, "\nRun `konstera plugin activate %s` to add it to its IDE.\n", p.Slug)
		}
	}
	return nil
}
