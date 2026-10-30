package plugins

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
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

func TestNextStepHint_ClaudeCodePrintsQuotedPluginDirCommand(t *testing.T) {
	path := `C:\Users\Jane Doe\.konstera\plugins\claude-code`
	hint := nextStepHint("claude-code", path)

	want := `claude --plugin-dir "C:\Users\Jane Doe\.konstera\plugins\claude-code"`
	if !strings.Contains(hint, want) {
		t.Errorf("hint missing %q:\n%s", want, hint)
	}
	if !strings.Contains(hint, "does not currently load") {
		t.Errorf("hint must say activate does not load the plugin:\n%s", hint)
	}
	if strings.Contains(hint, "Next: run `konstera plugin activate") {
		t.Errorf("hint must not send users to activate:\n%s", hint)
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

func TestActivate_OutputSaysLinkDoesNotLoadAndGivesCommand(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"1.2.3"}`)

	var out bytes.Buffer
	if err := Activate(&out, "claude-code"); err != nil {
		t.Fatal(err)
	}
	got := out.String()
	for _, want := range []string{
		"does not currently load",
		`claude --plugin-dir "` + dir + `"`,
	} {
		if !strings.Contains(got, want) {
			t.Errorf("output missing %q:\n%s", want, got)
		}
	}
	if strings.Contains(got, "Activated claude-code") || strings.Contains(got, "pick up the plugin") {
		t.Errorf("output still promises the plugin loads:\n%s", got)
	}
}

func TestInstalled_ReadsVersionsAndSkipsNonPlugins(t *testing.T) {
	home := setHome(t)
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

func TestInstalled_ForeignDirAtLinkPathIsNotActivated(t *testing.T) {
	home := setHome(t)
	fakeInstall(t, home, "claude-code", `{"version":"1.2.3"}`)
	dest, _, err := discoveryPath("claude-code")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(dest, 0o755); err != nil {
		t.Fatal(err)
	}

	got, err := Installed()
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].Activated != "no" {
		t.Errorf("got %+v", got)
	}
}

func TestList_ActivatedAfterActivate(t *testing.T) {
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"1.2.3"}`)
	if err := Activate(&bytes.Buffer{}, "claude-code"); err != nil {
		t.Fatal(err)
	}

	var out bytes.Buffer
	if err := List(&out); err != nil {
		t.Fatal(err)
	}
	fields := strings.Fields(strings.Split(out.String(), "\n")[1])
	if want := []string{"claude-code", "1.2.3", "yes"}; !reflect.DeepEqual(fields, want) {
		t.Errorf("row = %v, want %v\n%s", fields, want, out.String())
	}
	for _, want := range []string{"does not load claude-code", `claude --plugin-dir "` + dir + `"`} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("list must not imply activated means loaded; missing %q:\n%s", want, out.String())
		}
	}
}

// A junction is what activate creates on Windows without symlink privilege.
// Go 1.23 reports it as ModeIrregular, which inspect must still recognise.
func TestJunctionCountsAsActivatedAndDeactivates(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("junctions are Windows-only")
	}
	home := setHome(t)
	dir := fakeInstall(t, home, "claude-code", `{"version":"1.2.3"}`)
	dest, _, err := discoveryPath("claude-code")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		t.Fatal(err)
	}
	if out, err := exec.Command("cmd", "/C", "mklink", "/J", dest, dir).CombinedOutput(); err != nil {
		t.Fatalf("mklink /J: %v: %s", err, out)
	}

	if got := activationState("claude-code"); got != "yes" {
		t.Errorf("activationState = %q, want yes", got)
	}
	if err := Deactivate(&bytes.Buffer{}, "claude-code"); err != nil {
		t.Fatalf("Deactivate: %v", err)
	}
	if _, err := os.Lstat(dest); !os.IsNotExist(err) {
		t.Errorf("junction still present after deactivate: %v", err)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Errorf("install must survive deactivate: %v", err)
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
