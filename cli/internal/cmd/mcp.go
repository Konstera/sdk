package cmd

import (
	"fmt"
	"os"
	"regexp"

	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/mcpbridge"
	"github.com/Konstera/sdk/cli/internal/version"
	"github.com/spf13/cobra"
)

var clientNamePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,39}$`)

// newMCPCmd implements `konstera mcp`: a local MCP server over stdio for
// MCP clients that have no Konstera plugin (Claude Desktop, Cursor,
// Windsurf). The client starts it; nobody runs it by hand.
func newMCPCmd() *cobra.Command {
	var (
		apiURL     string
		clientName string
	)
	cmd := &cobra.Command{
		Use:   "mcp",
		Short: "Run the Konstera MCP server for Claude Desktop and other MCP clients (stdio)",
		Long: `Run a local MCP server over stdio that gives an MCP client the Konstera tools.

Claude Desktop (and Cursor, Windsurf, ...) starts this command itself; set it
up with 'konstera plugin activate claude-desktop' instead of running it.

Sign in from the client: call the konstera_sign_in tool. It opens the
Konstera portal in your browser for a tenant admin to approve. Each client
gets its own pairing (--client), kept in ~/.konstera/mcp-<client>.json and
renewed automatically. konstera_sign_out ends it.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if !clientNamePattern.MatchString(clientName) {
				return fmt.Errorf("--client must be lowercase letters, digits and dashes (got %q)", clientName)
			}
			base, err := resolveAPIBase(apiURL)
			if err != nil {
				return err
			}
			path, err := mcpbridge.SessionPath(clientName)
			if err != nil {
				return err
			}
			fingerprint, err := login.MachineFingerprint()
			if err != nil {
				return fmt.Errorf("compute machine fingerprint: %w", err)
			}
			session := mcpbridge.NewSession(path, login.NewClient(base))
			// The tenant must match the URL the pairing was made against.
			if c := session.Current(); c != nil && c.APIBaseURL != "" && c.APIBaseURL != base {
				fmt.Fprintf(os.Stderr, "konstera mcp: signed in against %s, but this server points at %s; sign out and in again to switch\n", c.APIBaseURL, base)
				base = c.APIBaseURL
				session = mcpbridge.NewSession(path, login.NewClient(base))
			}
			browser := openBrowser
			if os.Getenv("KONSTERA_NO_BROWSER") != "" {
				browser = nil // headless: the sign-in tool's reply carries the link
			}
			server := mcpbridge.NewServer(mcpbridge.Options{
				APIBase:     base,
				ClientName:  clientName,
				Version:     version.Version,
				Fingerprint: fingerprint,
				OpenBrowser: browser,
			}, session, os.Stderr)
			// stdout carries the protocol only; everything else goes to stderr.
			return server.Serve(cmd.Context(), os.Stdin, os.Stdout)
		},
	}
	cmd.Flags().StringVar(&apiURL, "api-url", "",
		"Konstera Platform API URL (default: KONSTERA_API_URL, then credentials.json, then https://api.konstera.ai)")
	cmd.Flags().StringVar(&clientName, "client", "claude-desktop",
		"Name of the MCP client; recorded on the pairing and names its session file")
	return cmd
}
