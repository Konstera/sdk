package cmd

import (
	"fmt"
	"strings"

	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/plugins"
	"github.com/spf13/cobra"
)

// newPluginCmd exposes `konstera plugin ...` subcommands. `uninstall` lands
// in a follow-up slice when there's a second plugin to manage.
func newPluginCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "plugin",
		Short: "Install and manage Konstera plugins for coding agents",
		// Backtick-wrapped command names (`konstera plugin install …`) in
		// cobra help text would close this raw string early — Go has no
		// escape for backticks inside backtick strings. Use plain prose
		// without backticks; cobra renders the help text as-is.
		Long: `Install and manage Konstera plugins for coding agents.

Each plugin wraps the Konstera MCP server for one specific IDE — Claude
Code, Cursor, Antigravity, etc. — so your editor can see Konstera tenant
shape and act on it without you having to hand-edit MCP config files.

Plugins are distributed by the Konstera Platform. 'konstera plugin
install <slug>' downloads the latest release, verifies its sha256, and
extracts to ~/.konstera/plugins/<slug>/. The next step is IDE-specific
(e.g. Claude Code needs --plugin-dir pointing at the extracted
directory); the install command prints the exact invocation.`,
	}
	cmd.AddCommand(
		newPluginInstallCmd(),
		newPluginListCmd(),
		newPluginActivateCmd(),
		newPluginDeactivateCmd(),
	)
	return cmd
}

func newPluginListCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List installed plugins with their version and activation state",
		Long: `List the plugins installed under ~/.konstera/plugins/.

Shows each plugin's slug, installed version, and whether its per-IDE link
from 'konstera plugin activate' is in place. VERSION is "unknown" when the
plugin doesn't record one. ACTIVATED is "yes", "no", or "n/a" for a slug
with no activation handler.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			return plugins.List(cmd.OutOrStdout())
		},
	}
}

func newPluginActivateCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "activate <slug>",
		Short: "Link an installed plugin into its IDE (does not load it in Claude Code; see --help)",
		// Keep Long free of inner backticks — Go has no escape for backticks
		// in backtick-delimited raw strings. Use plain prose.
		Long: `Link an installed plugin into its target IDE's plugin directory.

After 'konstera plugin install <slug>' extracts a plugin into
~/.konstera/plugins/<slug>/, this subcommand creates the per-IDE link.

For claude-code: symlinks ~/.konstera/plugins/claude-code into
~/.claude/plugins/claude-code (or a directory junction on Windows if
symlink privilege isn't held).

Known limitation: this link does not currently load the plugin. Claude
Code (tested on 2.1.314) ignores it. To load the plugin, start Claude
Code with the command 'konstera plugin install' prints:

  claude --plugin-dir "<path to ~/.konstera/plugins/claude-code>"

Supported slugs: ` + strings.Join(plugins.SupportedActivateSlugs(), ", ") + `.

Idempotent — a correct link already in place is reported as "already
linked" and succeeds without changes.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return plugins.Activate(cmd.OutOrStdout(), args[0])
		},
	}
}

func newPluginDeactivateCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "deactivate <slug>",
		Short: "Remove the per-IDE activation link (leaves the install in place)",
		Long: `Remove the per-IDE activation link for a plugin without
uninstalling it. The plugin files stay at ~/.konstera/plugins/<slug>/;
only the symlink into the IDE's discovery directory is removed.

Idempotent — nothing to remove is reported and succeeds.

Refuses to remove a link that doesn't point at a Konstera-managed
install, or a plain directory someone else created. Those cases are
flagged as errors so you can resolve them manually.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return plugins.Deactivate(cmd.OutOrStdout(), args[0])
		},
	}
}

func newPluginInstallCmd() *cobra.Command {
	var (
		apiURL string
		force  bool
	)
	cmd := &cobra.Command{
		Use:   "install <slug>",
		Short: "Install a Konstera plugin (claude-code, cursor, …)",
		Long: `Download, verify, and extract a Konstera plugin by slug.

Resolves the Konstera API URL from --api-url, KONSTERA_API_URL, your
~/.konstera/credentials.json (if you've run 'konstera login'), or the
default https://api.konstera.ai. The plugin is extracted into
~/.konstera/plugins/<slug>/.

If the slug is already installed and the installed version matches the
latest, the command exits successfully without re-downloading. Pass
--force to replace the existing install regardless.

Examples:
  konstera plugin install claude-code
  konstera plugin install claude-code --force
  konstera plugin install claude-code --api-url http://localhost:4500
`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			slug := args[0]
			base, err := resolveAPIBase(apiURL)
			if err != nil {
				return err
			}
			res, err := plugins.Install(cmd.Context(), cmd.OutOrStdout(), plugins.Options{
				Slug:       slug,
				APIBaseURL: base,
				Force:      force,
			})
			if err != nil {
				return err
			}
			if res.ReleaseNotes != "" {
				fmt.Fprintf(cmd.OutOrStdout(), "\nRelease notes:\n%s\n", res.ReleaseNotes)
			}
			fmt.Fprintln(cmd.OutOrStdout())
			fmt.Fprintln(cmd.OutOrStdout(), res.NextStepHint)
			return nil
		},
	}
	cmd.Flags().StringVar(&apiURL, "api-url", "",
		"Konstera Platform API URL (overrides KONSTERA_API_URL env + credentials.json)")
	cmd.Flags().BoolVar(&force, "force", false,
		"Replace an existing install at the target path")
	return cmd
}

// resolveAPIBase picks the Konstera API URL to query, in order:
//   1. --api-url flag
//   2. KONSTERA_API_URL env
//   3. api_base_url from ~/.konstera/credentials.json (if logged in)
//   4. https://api.konstera.ai (default)
func resolveAPIBase(flagValue string) (string, error) {
	if flagValue != "" {
		return flagValue, nil
	}
	if env := envOrDefault("KONSTERA_API_URL", ""); env != "" {
		return env, nil
	}
	if creds, err := login.LoadCredentials(); err == nil && creds != nil && creds.APIBaseURL != "" {
		return creds.APIBaseURL, nil
	}
	return "https://api.konstera.ai", nil
}
