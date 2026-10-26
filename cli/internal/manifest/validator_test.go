package manifest_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Konstera/sdk/cli/internal/manifest"
)

func writeTmp(t *testing.T, name, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write %s: %v", name, err)
	}
	return path
}

func schemaPath(t *testing.T) string {
	t.Helper()
	// Walk up to the sdk/ root to find schemas/agent-manifest.v3.json.
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	dir := cwd
	for i := 0; i < 8; i++ {
		candidate := filepath.Join(dir, "schemas", "agent-manifest.v3.json")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	t.Skip("agent-manifest.v3.json not found; run tests from inside sdk/")
	return ""
}

func TestValidate_ValidMinimalManifest(t *testing.T) {
	schema := schemaPath(t)
	body := `{
  "manifestVersion": 3,
  "id": "io.konstera.hello-cli-test",
  "name": "Hello CLI Test",
  "version": "0.1.0",
  "runtime": { "kind": "container", "image": "ghcr.io/konstera/hello:0.1.0" }
}`
	path := writeTmp(t, "manifest.json", body)

	result, err := manifest.Validate(schema, path)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if !result.Valid() {
		for _, e := range result.Errors() {
			t.Logf("  violation: %s — %s", e.Field(), e.Description())
		}
		t.Fatalf("expected valid, got %d errors", len(result.Errors()))
	}
}

func TestValidate_RejectsMissingRequiredFields(t *testing.T) {
	schema := schemaPath(t)
	// Missing: manifestVersion, runtime
	body := `{
  "id": "io.konstera.hello-cli-test",
  "name": "Hello",
  "version": "0.1.0"
}`
	path := writeTmp(t, "manifest.json", body)

	result, err := manifest.Validate(schema, path)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if result.Valid() {
		t.Fatal("expected invalid manifest to be rejected")
	}
	if len(result.Errors()) == 0 {
		t.Fatal("expected at least one schema violation")
	}
}

func TestValidate_RejectsBadIdPattern(t *testing.T) {
	schema := schemaPath(t)
	body := `{
  "manifestVersion": 3,
  "id": "NotReverseDNS",
  "name": "Hello",
  "version": "0.1.0",
  "runtime": { "kind": "container", "image": "x:1" }
}`
	path := writeTmp(t, "manifest.json", body)

	result, err := manifest.Validate(schema, path)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if result.Valid() {
		t.Fatal("expected invalid id to be rejected")
	}
}
