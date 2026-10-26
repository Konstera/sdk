// Package imagebuild wraps `docker buildx build`, reading the agent id + version
// from manifest.json so users rarely need to pass flags. Named `imagebuild`
// rather than `build` to avoid colliding with the repo-root `.gitignore` rule
// that excludes `**/build/` (Python wheel-output convention).
package imagebuild

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
)

// Options control a build.
type Options struct {
	ManifestPath string // path to manifest.json; defaults to ./manifest.json
	Context      string // docker build context; defaults to the manifest's dir
	Dockerfile   string // path to Dockerfile; defaults to <context>/Dockerfile
	Tag          string // image tag; defaults to <id>:<version> from the manifest
	Push         bool   // if true, pass --push to docker buildx
	Platform     string // optional --platform value (e.g. "linux/amd64,linux/arm64")
	Stdout       io.Writer
	Stderr       io.Writer
}

// Manifest is the subset of the agent manifest the builder reads.
type Manifest struct {
	ID      string `json:"id"`
	Version string `json:"version"`
	Runtime struct {
		Image string `json:"image"`
	} `json:"runtime"`
}

// LoadManifest parses the manifest JSON file.
func LoadManifest(path string) (*Manifest, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}
	var m Manifest
	if err := json.Unmarshal(body, &m); err != nil {
		return nil, fmt.Errorf("parse manifest: %w", err)
	}
	if m.ID == "" || m.Version == "" {
		return nil, fmt.Errorf("manifest %s: id + version are required", path)
	}
	return &m, nil
}

// BuildCommand assembles the `docker buildx build` command without running it.
// Exported so tests can assert on the final arg list.
func BuildCommand(opts Options, m *Manifest) ([]string, error) {
	tag := opts.Tag
	if tag == "" {
		tag = m.ID + ":" + m.Version
	}
	ctx := opts.Context
	if ctx == "" {
		ctx = filepath.Dir(opts.ManifestPath)
	}
	dockerfile := opts.Dockerfile
	if dockerfile == "" {
		dockerfile = filepath.Join(ctx, "Dockerfile")
	}

	args := []string{"buildx", "build", "-t", tag, "-f", dockerfile}
	if opts.Platform != "" {
		args = append(args, "--platform", opts.Platform)
	}
	if opts.Push {
		args = append(args, "--push")
	} else {
		args = append(args, "--load")
	}
	args = append(args, ctx)
	return args, nil
}

// Run executes `docker` with the args from BuildCommand. Streams output to
// opts.Stdout / opts.Stderr (defaults to os.Stdout / os.Stderr).
func Run(opts Options) error {
	if opts.ManifestPath == "" {
		opts.ManifestPath = "./manifest.json"
	}
	m, err := LoadManifest(opts.ManifestPath)
	if err != nil {
		return err
	}
	args, err := BuildCommand(opts, m)
	if err != nil {
		return err
	}

	stdout := opts.Stdout
	if stdout == nil {
		stdout = os.Stdout
	}
	stderr := opts.Stderr
	if stderr == nil {
		stderr = os.Stderr
	}

	fmt.Fprintf(stdout, "+ docker %s\n", joinArgs(args))
	cmd := exec.Command("docker", args...)
	cmd.Stdout = stdout
	cmd.Stderr = stderr
	return cmd.Run()
}

func joinArgs(args []string) string {
	out := ""
	for i, a := range args {
		if i > 0 {
			out += " "
		}
		out += a
	}
	return out
}
