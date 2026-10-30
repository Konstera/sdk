// Package plugins implements `konstera plugin install <slug>` — the client
// side of the Platform-served plugin-release registry (ADR-057 M1).
//
// The install flow:
//
//  1. GET {api}/api/plugins/{slug}/latest → metadata + absolute download URL
//     + sha256.
//  2. Download the tarball to a temp file alongside the plugins dir.
//  3. SHA-256 the bytes locally and compare against the metadata — refuse
//     to extract if they disagree.
//  4. Extract into a per-slug staging dir, then atomically rename over
//     ~/.konstera/plugins/<slug>/ (replacing any previous install).
//  5. Print install instructions for the host IDE.
//
// Design: the tarball's internal root is named `konstera-<slug>-<version>/`
// (per the plugins-repo pack script). We strip that prefix on extract so
// the per-slug directory contains plugin files directly, not nested
// another level — the user's final path is predictable.
package plugins

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
)

// Metadata is what GET /api/plugins/{slug}/latest returns.
type Metadata struct {
	Slug         string    `json:"slug"`
	Version      string    `json:"version"`
	Filename     string    `json:"filename"`
	Sha256       string    `json:"sha256"`
	SizeBytes    int64     `json:"size_bytes"`
	DownloadURL  string    `json:"download_url"`
	PublishedAt  time.Time `json:"published_at"`
	PublishedBy  string    `json:"published_by,omitempty"`
	ReleaseNotes string    `json:"release_notes,omitempty"`
}

// Options control an install.
type Options struct {
	// Slug of the plugin to install (e.g. "claude-code").
	Slug string
	// APIBaseURL overrides the Konstera API URL. Resolution order used by
	// the CLI command: --api-url flag > KONSTERA_API_URL env > credentials
	// file > "https://api.konstera.ai".
	APIBaseURL string
	// Force replaces any existing install at the target path. Without this,
	// an existing directory is treated as success (idempotent re-run) if
	// the installed version matches, or an error otherwise.
	Force bool
	// Version pins a specific version to install. Empty means "latest".
	// Reserved; the current implementation always installs latest.
	Version string
}

// InstallResult is what a successful install returns.
type InstallResult struct {
	Slug            string
	Version         string
	InstalledPath   string
	ReleaseNotes    string
	NextStepHint    string // IDE-specific "now do X" instruction
}

// Install resolves + downloads + verifies + extracts a plugin.
func Install(ctx context.Context, out io.Writer, opts Options) (*InstallResult, error) {
	if opts.Slug == "" {
		return nil, errors.New("slug is required")
	}
	api := strings.TrimRight(opts.APIBaseURL, "/")
	if api == "" {
		return nil, errors.New("APIBaseURL is required (CLI resolves from --api-url / env / credentials / default)")
	}

	fmt.Fprintf(out, "Fetching latest %s release from %s…\n", opts.Slug, api)
	meta, err := fetchLatest(ctx, api, opts.Slug)
	if err != nil {
		return nil, err
	}

	targetDir, err := targetPath(opts.Slug)
	if err != nil {
		return nil, err
	}

	// Idempotent short-circuit: if the slug is already installed and the
	// installed version matches, do nothing. --force bypasses this.
	if !opts.Force {
		if installed, ok := readInstalledVersion(targetDir); ok && installed == meta.Version {
			fmt.Fprintf(out, "%s %s is already installed at %s.\n", opts.Slug, meta.Version, targetDir)
			return &InstallResult{
				Slug:          opts.Slug,
				Version:       meta.Version,
				InstalledPath: targetDir,
				NextStepHint:  nextStepHint(opts.Slug, targetDir),
			}, nil
		}
	}

	fmt.Fprintf(out, "Downloading %s (%d bytes)…\n", meta.Filename, meta.SizeBytes)
	tarPath, err := downloadTarball(ctx, meta)
	if err != nil {
		return nil, err
	}
	defer os.Remove(tarPath)

	fmt.Fprintf(out, "Verifying sha256…\n")
	if err := verifySha256(tarPath, meta.Sha256); err != nil {
		return nil, err
	}

	fmt.Fprintf(out, "Extracting into %s…\n", targetDir)
	if err := extractAtomic(tarPath, targetDir, opts.Slug); err != nil {
		return nil, err
	}

	fmt.Fprintf(out, "Installed %s %s.\n", opts.Slug, meta.Version)
	return &InstallResult{
		Slug:          opts.Slug,
		Version:       meta.Version,
		InstalledPath: targetDir,
		ReleaseNotes:  meta.ReleaseNotes,
		NextStepHint:  nextStepHint(opts.Slug, targetDir),
	}, nil
}

// -- registry client ----------------------------------------------------

func fetchLatest(ctx context.Context, api, slug string) (*Metadata, error) {
	u := fmt.Sprintf("%s/api/plugins/%s/latest", api, url.PathEscape(slug))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("reaching Konstera at %s: %w", api, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("no releases published for plugin %q — check the slug or ask the Konstera team", slug)
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return nil, fmt.Errorf("registry returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var meta Metadata
	if err := json.NewDecoder(resp.Body).Decode(&meta); err != nil {
		return nil, fmt.Errorf("decoding registry response: %w", err)
	}
	if meta.DownloadURL == "" || meta.Sha256 == "" || meta.Version == "" {
		return nil, errors.New("registry response is missing required fields (download_url / sha256 / version)")
	}
	return &meta, nil
}

func downloadTarball(ctx context.Context, meta *Metadata) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, meta.DownloadURL, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("downloading tarball: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("tarball download returned %d", resp.StatusCode)
	}

	home, err := login.KonsteraHome()
	if err != nil {
		return "", err
	}
	tmp, err := os.CreateTemp(home, ".plugin-"+meta.Slug+"-*.tgz")
	if err != nil {
		return "", err
	}
	defer tmp.Close()
	if _, err := io.Copy(tmp, resp.Body); err != nil {
		_ = os.Remove(tmp.Name())
		return "", err
	}
	return tmp.Name(), nil
}

// -- verification + extraction -----------------------------------------

func verifySha256(path, expected string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	actual := hex.EncodeToString(h.Sum(nil))
	if !strings.EqualFold(actual, expected) {
		return fmt.Errorf("sha256 mismatch: expected %s, got %s — the tarball is corrupted or tampered with", expected, actual)
	}
	return nil
}

// extractAtomic extracts tarPath into a staging dir, then renames over
// targetDir — so a crashed extract leaves no half-installed plugin, and a
// successful install swaps the whole directory in one filesystem op.
func extractAtomic(tarPath, targetDir, slug string) error {
	parent := filepath.Dir(targetDir)
	if err := os.MkdirAll(parent, 0o700); err != nil {
		return err
	}
	staging, err := os.MkdirTemp(parent, ".plugin-"+slug+"-stage-*")
	if err != nil {
		return err
	}
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.RemoveAll(staging)
		}
	}()

	if err := extractToDir(tarPath, staging, slug); err != nil {
		return err
	}

	// Replace targetDir atomically. On Windows os.Rename over an existing
	// directory fails; we remove-then-rename and accept a brief window
	// where the plugin is absent. For a dev-tool install this is fine.
	backup := ""
	if _, err := os.Stat(targetDir); err == nil {
		backup = targetDir + ".old-" + fmt.Sprint(time.Now().UnixNano())
		if err := os.Rename(targetDir, backup); err != nil {
			return fmt.Errorf("moving existing install aside: %w", err)
		}
	}
	if err := os.Rename(staging, targetDir); err != nil {
		// Try to restore the backup if the rename-in failed.
		if backup != "" {
			_ = os.Rename(backup, targetDir)
		}
		return fmt.Errorf("installing new version: %w", err)
	}
	cleanup = false
	if backup != "" {
		_ = os.RemoveAll(backup)
	}
	return nil
}

// extractToDir extracts the tar.gz at tarPath into dst, stripping the top-
// level `konstera-<slug>-<version>/` directory the pack script wrote. If
// the tarball doesn't have that prefix (e.g. a hand-rolled archive), we
// fall back to extracting as-is.
func extractToDir(tarPath, dst, slug string) error {
	f, err := os.Open(tarPath)
	if err != nil {
		return err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return fmt.Errorf("not a gzip stream: %w", err)
	}
	defer gz.Close()
	tr := tar.NewReader(gz)

	expectedPrefix := "konstera-" + slug + "-"

	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		name := hdr.Name
		// Strip the single top-level directory. Both forms are accepted
		// so a hand-rolled flat tar still works.
		if idx := strings.Index(name, "/"); idx >= 0 && strings.HasPrefix(name, expectedPrefix) {
			name = name[idx+1:]
			if name == "" {
				continue // the top-level dir entry itself
			}
		}
		// Prevent path-traversal: no absolute paths, no "..".
		if filepath.IsAbs(name) || strings.Contains(name, "..") {
			return fmt.Errorf("tarball contains unsafe path %q", hdr.Name)
		}
		target := filepath.Join(dst, filepath.FromSlash(name))

		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
			if err != nil {
				return err
			}
			if _, err := io.Copy(out, tr); err != nil {
				_ = out.Close()
				return err
			}
			if err := out.Close(); err != nil {
				return err
			}
		case tar.TypeSymlink, tar.TypeLink:
			// Plugin tarballs produced by our pack script don't contain
			// symlinks — refuse them to keep extraction behaviour simple.
			return fmt.Errorf("tarball contains a symlink (%s → %s); plugins must be plain files", hdr.Name, hdr.Linkname)
		default:
			// Skip unknown types quietly — same reasoning as symlinks.
		}
	}
	return nil
}

// -- paths + hints ------------------------------------------------------

// pluginsDir is the directory holding every installed plugin.
func pluginsDir() (string, error) {
	home, err := login.KonsteraHome()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "plugins"), nil
}

func targetPath(slug string) (string, error) {
	dir, err := pluginsDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, slug), nil
}

// readInstalledVersion reads the version field out of the plugin's
// .claude-plugin/plugin.json (for claude-code plugins) if present. Returns
// ("", false) for every other case; the caller treats that as "not
// installed" or "installed but version unknown — re-extract".
func readInstalledVersion(dir string) (string, bool) {
	for _, candidate := range []string{
		filepath.Join(dir, ".claude-plugin", "plugin.json"),
	} {
		b, err := os.ReadFile(candidate)
		if err != nil {
			continue
		}
		var manifest struct {
			Version string `json:"version"`
		}
		if err := json.Unmarshal(b, &manifest); err != nil {
			continue
		}
		if manifest.Version != "" {
			return manifest.Version, true
		}
	}
	return "", false
}

// nextStepHint prints the IDE-specific "what to do now" instruction.
// For Claude Code that is the --plugin-dir launch command: the link made by
// `konstera plugin activate` does not load the plugin (see activate.go).
// Other IDEs will add their own case as plugins ship for them.
func nextStepHint(slug, installedPath string) string {
	switch slug {
	case "claude-code":
		return claudeCodeLoadSteps("Next: start Claude Code with the plugin loaded (the flag applies to that session only):", installedPath) +
			"\n\nNote: `konstera plugin activate claude-code` does not currently load the plugin.\n" +
			"Claude Code (tested on 2.1.314) ignores the link it creates in ~/.claude/plugins."
	default:
		return fmt.Sprintf("Installed at %s. See the plugin's README for activation instructions.", installedPath)
	}
}

// claudeCodeLoadSteps renders the working way to load an installed plugin.
// Double quotes are the one form cmd.exe, PowerShell and POSIX shells all
// accept for a path with spaces.
func claudeCodeLoadSteps(lead, installedPath string) string {
	return fmt.Sprintf("%s\n\n  claude --plugin-dir \"%s\"\n\nThen run /konstera-signin inside Claude Code.", lead, installedPath)
}

