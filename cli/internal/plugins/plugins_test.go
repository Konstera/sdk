package plugins

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// setHome points every home lookup at a temp dir, so tests never touch the
// real ~/.konstera or ~/.claude.
func setHome(t *testing.T) string {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
	t.Setenv("KONSTERA_HOME", "")
	return home
}

// fakeInstall creates ~/.konstera/plugins/<slug>/, with the given
// plugin.json content unless it is empty.
func fakeInstall(t *testing.T, home, slug, manifest string) string {
	t.Helper()
	dir := filepath.Join(home, ".konstera", "plugins", slug)
	if err := os.MkdirAll(filepath.Join(dir, ".claude-plugin"), 0o755); err != nil {
		t.Fatal(err)
	}
	if manifest != "" {
		path := filepath.Join(dir, ".claude-plugin", "plugin.json")
		if err := os.WriteFile(path, []byte(manifest), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

// fakeClaude replaces the claude command and records every call. list is
// what `claude plugin list --json` answers.
func fakeClaude(t *testing.T, list string) *[][]string {
	t.Helper()
	calls := &[][]string{}
	original := runClaude
	runClaude = func(args ...string) (string, error) {
		*calls = append(*calls, args)
		if len(args) > 1 && args[1] == "list" {
			return list, nil
		}
		return "", nil
	}
	t.Cleanup(func() { runClaude = original })
	return calls
}

const claudeListsKonstera = `[{"id":"konstera@konstera","enabled":true}]`

func TestNextStepHint_ClaudeCodePointsAtActivate(t *testing.T) {
	hint := nextStepHint("claude-code", `C:\Users\Jane Doe\.konstera\plugins\claude-code`)
	for _, want := range []string{"konstera plugin activate claude-code", "/konstera-signin"} {
		if !strings.Contains(hint, want) {
			t.Errorf("hint missing %q:\n%s", want, hint)
		}
	}
	if strings.Contains(hint, "--plugin-dir") {
		t.Errorf("no user should need --plugin-dir:\n%s", hint)
	}
}

func TestNextStepHint_OtherSlugsPointAtTheirReadme(t *testing.T) {
	hint := nextStepHint("cursor", "/x/cursor")
	if !strings.Contains(hint, "/x/cursor") || !strings.Contains(hint, "README") {
		t.Errorf("unexpected hint: %s", hint)
	}
	if strings.Contains(hint, "--plugin-dir") {
		t.Errorf("--plugin-dir is Claude Code specific: %s", hint)
	}
}

func TestActivate_InstallsThroughClaudeCode(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	calls := fakeClaude(t, "[]")

	var out bytes.Buffer
	if err := Activate(&out, "claude-code", "https://api.konstera.test"); err != nil {
		t.Fatalf("Activate: %v", err)
	}

	root := filepath.Dir(dir)
	want := [][]string{
		{"plugin", "marketplace", "add", root},
		{"plugin", "install", "konstera@konstera", "--config", "base_url=https://api.konstera.test"},
	}
	if !reflect.DeepEqual(*calls, want) {
		t.Errorf("claude calls:\n got %v\nwant %v", *calls, want)
	}
	body, err := os.ReadFile(filepath.Join(root, ".claude-plugin", "marketplace.json"))
	if err != nil {
		t.Fatalf("marketplace.json: %v", err)
	}
	var marketplace struct {
		Name    string
		Plugins []struct{ Name, Source string }
	}
	if err := json.Unmarshal(body, &marketplace); err != nil {
		t.Fatalf("marketplace.json: %v", err)
	}
	if marketplace.Name != "konstera" || marketplace.Plugins[0].Name != "konstera" ||
		marketplace.Plugins[0].Source != "./claude-code" {
		t.Errorf("marketplace.json = %+v", marketplace)
	}
	if !strings.Contains(out.String(), "/konstera-signin") || strings.Contains(out.String(), "--plugin-dir") {
		t.Errorf("output: %s", out.String())
	}
}

func TestActivate_FailsWhenClaudeCodeFails(t *testing.T) {
	home := setHome(t)
	fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	original := runClaude
	runClaude = func(args ...string) (string, error) {
		return "marketplace refused", errors.New("exit status 1")
	}
	t.Cleanup(func() { runClaude = original })

	var out bytes.Buffer
	err := Activate(&out, "claude-code", "https://api.konstera.test")

	if err == nil || !strings.Contains(err.Error(), "marketplace refused") {
		t.Fatalf("Activate must report the refusal, got %v", err)
	}
	if strings.Contains(out.String(), "✓") {
		t.Errorf("no success line on failure: %s", out.String())
	}
}

func TestActivate_ExplainsMissingClaudeCode(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	original := runClaude
	runClaude = func(args ...string) (string, error) { return "", errClaudeNotFound }
	t.Cleanup(func() { runClaude = original })

	err := Activate(&bytes.Buffer{}, "claude-code", "https://api.konstera.test")

	if err == nil || !strings.Contains(err.Error(), "Install Claude Code") || !strings.Contains(err.Error(), dir) {
		t.Fatalf("got %v", err)
	}
}

func TestActivate_NotInstalled(t *testing.T) {
	setHome(t)
	calls := fakeClaude(t, "[]")

	err := Activate(&bytes.Buffer{}, "claude-code", "https://api.konstera.test")

	if err == nil || !strings.Contains(err.Error(), "konstera plugin install") {
		t.Fatalf("got %v", err)
	}
	if len(*calls) != 0 {
		t.Errorf("claude must not run: %v", *calls)
	}
}

// The link older CLIs left behind is gone after activate; a directory that
// is not ours stays.
func TestActivate_RemovesOnlyOurLegacyLink(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	fakeClaude(t, "[]")
	plugins := filepath.Join(home, ".claude", "plugins")
	if err := os.MkdirAll(plugins, 0o755); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(plugins, "claude-code")
	if err := os.Symlink(dir, link); err != nil {
		t.Skipf("symlink not available: %v", err)
	}

	if err := Activate(&bytes.Buffer{}, "claude-code", "https://api.konstera.test"); err != nil {
		t.Fatalf("Activate: %v", err)
	}
	if _, err := os.Lstat(link); !os.IsNotExist(err) {
		t.Errorf("legacy link still present: %v", err)
	}

	if err := os.Mkdir(link, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := Activate(&bytes.Buffer{}, "claude-code", "https://api.konstera.test"); err != nil {
		t.Fatalf("Activate: %v", err)
	}
	if _, err := os.Stat(link); err != nil {
		t.Errorf("foreign directory removed: %v", err)
	}
}

func TestInstalled_ReadsVersionsAndSkipsNonPlugins(t *testing.T) {
	home := setHome(t)
	fakeClaude(t, "[]")
	fakeInstall(t, home, "claude-code", `{"name":"konstera","version":"1.2.3"}`)
	fakeInstall(t, home, "no-manifest", "")
	fakeInstall(t, home, "bad-json", `{not json`)
	fakeInstall(t, home, "no-version", `{"name":"x"}`)
	// Leftovers of an interrupted install, and a stray file: not plugins.
	fakeInstall(t, home, ".plugin-claude-code-stage-123", `{"version":"9"}`)
	fakeInstall(t, home, "claude-code.old-123", `{"version":"9"}`)
	stray := filepath.Join(home, ".konstera", "plugins", "notes.txt")
	if err := os.WriteFile(stray, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	got, err := Installed()
	if err != nil {
		t.Fatal(err)
	}
	want := []InstalledPlugin{
		{"bad-json", "unknown", "n/a"},
		{"claude-code", "1.2.3", "no"},
		{"no-manifest", "unknown", "n/a"},
		{"no-version", "unknown", "n/a"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got  %+v\nwant %+v", got, want)
	}
}

func TestList_ReportsWhatClaudeCodeSays(t *testing.T) {
	home := setHome(t)
	fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	fakeClaude(t, claudeListsKonstera)

	var out bytes.Buffer
	if err := List(&out); err != nil {
		t.Fatalf("List: %v", err)
	}
	if !strings.Contains(out.String(), "yes") || strings.Contains(out.String(), "plugin activate") {
		t.Errorf("list:\n%s", out.String())
	}
}

func TestList_OffersActivateWhenClaudeCodeLacksThePlugin(t *testing.T) {
	home := setHome(t)
	fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	fakeClaude(t, `[{"id":"konstera@konstera","enabled":false}]`)

	var out bytes.Buffer
	if err := List(&out); err != nil {
		t.Fatalf("List: %v", err)
	}
	if !strings.Contains(out.String(), "konstera plugin activate claude-code") {
		t.Errorf("list:\n%s", out.String())
	}
}

func TestDeactivate_RemovesFromClaudeCodeAndKeepsInstall(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	calls := fakeClaude(t, claudeListsKonstera)

	if err := Deactivate(&bytes.Buffer{}, "claude-code"); err != nil {
		t.Fatalf("Deactivate: %v", err)
	}

	want := [][]string{
		{"plugin", "list", "--json"},
		{"plugin", "uninstall", "konstera@konstera"},
		{"plugin", "marketplace", "remove", "konstera"},
	}
	if !reflect.DeepEqual(*calls, want) {
		t.Errorf("claude calls:\n got %v\nwant %v", *calls, want)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Errorf("install must survive deactivate: %v", err)
	}
}

func TestDeactivate_NothingActiveIsFine(t *testing.T) {
	home := setHome(t)
	fakeInstall(t, home, "claude-code", `{"version":"0.2.0"}`)
	calls := fakeClaude(t, "[]")

	if err := Deactivate(&bytes.Buffer{}, "claude-code"); err != nil {
		t.Fatalf("Deactivate: %v", err)
	}
	if len(*calls) != 1 {
		t.Errorf("only the list call expected: %v", *calls)
	}
}

func TestList_EmptyStateIsHelpful(t *testing.T) {
	for name, prepare := range map[string]func(t *testing.T, home string){
		"no plugins dir": func(t *testing.T, home string) {},
		"empty plugins dir": func(t *testing.T, home string) {
			if err := os.MkdirAll(filepath.Join(home, ".konstera", "plugins"), 0o755); err != nil {
				t.Fatal(err)
			}
		},
	} {
		t.Run(name, func(t *testing.T) {
			home := setHome(t)
			prepare(t, home)
			var out bytes.Buffer
			if err := List(&out); err != nil {
				t.Fatalf("empty state must succeed: %v", err)
			}
			if !strings.Contains(out.String(), "konstera plugin install") {
				t.Errorf("unhelpful empty state: %q", out.String())
			}
		})
	}
}
