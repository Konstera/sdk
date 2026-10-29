package cmd

import (
	"fmt"

	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/plugins"
	"github.com/spf13/cobra"
)

// newPluginCmd exposes `konstera plugin ...` subcommands. Currently just
// `install`; `list` + `uninstall` land in a follow-up slice when there's
// a second plugin to manage.
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
	cmd.AddCommand(newPluginInstallCmd())
	return cmd
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
