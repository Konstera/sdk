package cmd

import (
	"bytes"
	"strings"
	"testing"
)

func TestPluginCmd_RegistersSubcommands(t *testing.T) {
	cmd := newPluginCmd()
	for _, name := range []string{"install", "list", "activate", "deactivate"} {
		sub, _, err := cmd.Find([]string{name})
		if err != nil || sub.Name() != name {
			t.Errorf("subcommand %q not registered: %v", name, err)
		}
	}
}

func TestPluginList_RunsAgainstEmptyHome(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
	t.Setenv("KONSTERA_HOME", "")

	cmd := newPluginCmd()
	var out bytes.Buffer
	cmd.SetOut(&out)
	cmd.SetArgs([]string{"list"})
	if err := cmd.Execute(); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "No plugins installed") {
		t.Errorf("unexpected output: %q", out.String())
	}
}

func TestPluginActivateHelp_DescribesTheMarketplaceInstall(t *testing.T) {
	long := newPluginActivateCmd().Long
	for _, want := range []string{"local Claude Code", "Claude Code must be installed first"} {
		if !strings.Contains(long, want) {
			t.Errorf("activate help missing %q:\n%s", want, long)
		}
	}
	if strings.Contains(long, "--plugin-dir") {
		t.Errorf("no user should need --plugin-dir:\n%s", long)
	}
}
