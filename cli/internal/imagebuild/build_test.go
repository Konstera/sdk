package imagebuild_test

import (
	"os"
	"path/filepath"
	"testing"

	build "github.com/Konstera/sdk/cli/internal/imagebuild"
)

func writeManifest(t *testing.T, dir, body string) string {
	t.Helper()
	path := filepath.Join(dir, "manifest.json")
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadManifest_HappyPath(t *testing.T) {
	path := writeManifest(t, t.TempDir(), `{
  "manifestVersion": 3,
  "id": "io.konstera.hello-build-test",
  "name": "Hello",
  "version": "0.1.0",
  "runtime": { "kind": "container", "image": "io.konstera.hello-build-test:0.1.0" }
}`)
	m, err := build.LoadManifest(path)
	if err != nil {
		t.Fatalf("LoadManifest: %v", err)
	}
	if m.ID != "io.konstera.hello-build-test" || m.Version != "0.1.0" {
		t.Errorf("got id=%q version=%q", m.ID, m.Version)
	}
}

func TestLoadManifest_RejectsMissingIdOrVersion(t *testing.T) {
	path := writeManifest(t, t.TempDir(), `{ "manifestVersion": 3, "name": "X" }`)
	if _, err := build.LoadManifest(path); err == nil {
		t.Fatal("expected error on missing id + version")
	}
}

func TestBuildCommand_DefaultTagFromManifest(t *testing.T) {
	m := &build.Manifest{ID: "io.konstera.my-agent", Version: "1.2.3"}
	args, err := build.BuildCommand(build.Options{ManifestPath: "./manifest.json"}, m)
	if err != nil {
		t.Fatal(err)
	}
	expectArg(t, args, "-t")
	expectArg(t, args, "io.konstera.my-agent:1.2.3")
	expectArg(t, args, "--load")
}

func TestBuildCommand_RespectsOverrides(t *testing.T) {
	m := &build.Manifest{ID: "x", Version: "0.1.0"}
	args, err := build.BuildCommand(build.Options{
		ManifestPath: "./manifest.json",
		Tag:          "registry.example.com/x:latest",
		Push:         true,
		Platform:     "linux/amd64,linux/arm64",
	}, m)
	if err != nil {
		t.Fatal(err)
	}
	expectArg(t, args, "registry.example.com/x:latest")
	expectArg(t, args, "--push")
	expectArg(t, args, "linux/amd64,linux/arm64")
	// --load must NOT be present when --push is set
	for _, a := range args {
		if a == "--load" {
			t.Error("--load should not be set when --push is true")
		}
	}
}

func expectArg(t *testing.T, args []string, want string) {
	t.Helper()
	for _, a := range args {
		if a == want {
			return
		}
	}
	t.Errorf("expected arg %q in %v", want, args)
}
