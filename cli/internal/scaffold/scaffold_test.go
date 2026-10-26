package scaffold_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Konstera/sdk/cli/internal/scaffold"
)

func TestCreate_Python_WritesExpectedFiles(t *testing.T) {
	dir := t.TempDir()
	err := scaffold.Create(scaffold.Options{
		Name:     "hello-cli-scaffold",
		Language: "python",
		Template: "hello-world",
		Dir:      dir,
		Force:    true,
	})
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	for _, name := range []string{"manifest.json", "main.py", "requirements.txt", "Dockerfile", ".dockerignore", "README.md"} {
		if _, err := os.Stat(filepath.Join(dir, name)); err != nil {
			t.Errorf("expected %s to exist: %v", name, err)
		}
	}
}

func TestCreate_PythonManifest_SubstitutesPlaceholders(t *testing.T) {
	dir := t.TempDir()
	if err := scaffold.Create(scaffold.Options{
		Name: "my-agent", Language: "python", Template: "hello-world", Dir: dir, Force: true,
	}); err != nil {
		t.Fatalf("Create: %v", err)
	}
	manifest := readFile(t, filepath.Join(dir, "manifest.json"))
	expectContains(t, manifest, `"id": "io.konstera.my-agent"`)
	expectContains(t, manifest, `"name": "My Agent"`)
	expectContains(t, manifest, `"version": "0.1.0"`)
	expectContains(t, manifest, `"image": "io.konstera.my-agent:0.1.0"`)

	main := readFile(t, filepath.Join(dir, "main.py"))
	expectContains(t, main, "class MyAgent(Agent):")
	expectContains(t, main, "Hello, {name}! From my-agent.")
}

func TestCreate_TypeScript_WritesExpectedFiles(t *testing.T) {
	dir := t.TempDir()
	if err := scaffold.Create(scaffold.Options{
		Name: "ts-agent", Language: "typescript", Template: "hello-world", Dir: dir, Force: true,
	}); err != nil {
		t.Fatalf("Create: %v", err)
	}
	for _, name := range []string{"manifest.json", "package.json", "tsconfig.json", "Dockerfile", "src/index.ts"} {
		if _, err := os.Stat(filepath.Join(dir, name)); err != nil {
			t.Errorf("expected %s to exist: %v", name, err)
		}
	}
	index := readFile(t, filepath.Join(dir, "src/index.ts"))
	expectContains(t, index, "class TsAgent extends Agent")
}

func TestCreate_Dotnet_RenamesCsproj(t *testing.T) {
	dir := t.TempDir()
	if err := scaffold.Create(scaffold.Options{
		Name: "net-agent", Language: "dotnet", Template: "hello-world", Dir: dir, Force: true,
	}); err != nil {
		t.Fatalf("Create: %v", err)
	}
	// project.csproj.tmpl is renamed to <AgentName>.csproj at render time
	if _, err := os.Stat(filepath.Join(dir, "net-agent.csproj")); err != nil {
		t.Errorf("expected net-agent.csproj: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "project.csproj")); err == nil {
		t.Errorf("unexpected project.csproj left over (should've been renamed)")
	}
	prog := readFile(t, filepath.Join(dir, "Program.cs"))
	expectContains(t, prog, `new Agent("io.konstera.net-agent")`)
}

func TestCreate_RejectsBadAgentName(t *testing.T) {
	for _, bad := range []string{"", "My-Agent", "my_agent", "1agent", "my agent", "AGENT"} {
		err := scaffold.Create(scaffold.Options{Name: bad, Language: "python", Template: "hello-world", Dir: t.TempDir(), Force: true})
		if err == nil {
			t.Errorf("expected rejection of %q", bad)
		}
	}
}

func TestCreate_RejectsBadLanguage(t *testing.T) {
	err := scaffold.Create(scaffold.Options{Name: "my-agent", Language: "cobol", Template: "hello-world", Dir: t.TempDir(), Force: true})
	if err == nil {
		t.Fatal("expected rejection of unsupported language")
	}
}

func TestCreate_RejectsNonEmptyDirWithoutForce(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "existing.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	err := scaffold.Create(scaffold.Options{Name: "my-agent", Language: "python", Template: "hello-world", Dir: dir, Force: false})
	if err == nil {
		t.Fatal("expected rejection of non-empty dir without --force")
	}
}

// -- helpers -----------------------------------------------------------

func readFile(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(b)
}

func expectContains(t *testing.T, haystack, needle string) {
	t.Helper()
	if !strings.Contains(haystack, needle) {
		t.Errorf("expected to find %q, got:\n%s", needle, haystack)
	}
}
