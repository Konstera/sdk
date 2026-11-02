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
extracts to ~/.konstera/plugins/<slug>/. 'konstera plugin activate
<slug>' then adds it to the IDE.`,
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

Shows each plugin's slug, installed version, and whether its IDE has it
enabled. VERSION is "unknown" when the plugin doesn't record one. ACTIVATED
is "yes", "no", or "n/a" for a slug with no activation handler.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			return plugins.List(cmd.OutOrStdout())
		},
	}
}

func newPluginActivateCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "activate <slug>",
		Short: "Add an installed plugin to its IDE",
		// Keep Long free of inner backticks — Go has no escape for backticks
		// in backtick-delimited raw strings. Use plain prose.
		Long: `Add an installed plugin to its target IDE.

After 'konstera plugin install <slug>' extracts a plugin into
~/.konstera/plugins/<slug>/, this subcommand makes the IDE load it.

For claude-code: registers ~/.konstera/plugins as a local Claude Code
marketplace and installs the plugin from it with the claude command, so
Claude Code must be installed first. The plugin loads in every new session,
with no flags. Upgrades from 'konstera plugin install --force' reach the
next session by themselves.

Supported slugs: ` + strings.Join(plugins.SupportedActivateSlugs(), ", ") + `.

Idempotent — safe to run again.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			base, err := resolveAPIBase("")
			if err != nil {
				return err
			}
			return plugins.Activate(cmd.OutOrStdout(), args[0], base)
		},
	}
}

func newPluginDeactivateCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "deactivate <slug>",
		Short: "Remove a plugin from its IDE (leaves the install in place)",
		Long: `Remove a plugin from its IDE without uninstalling it. The plugin
files stay at ~/.konstera/plugins/<slug>/.

Idempotent — nothing to remove is reported and succeeds.`,
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
