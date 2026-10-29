package cmd

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/version"
	"github.com/spf13/cobra"
)

// newLoginCmd implements `konstera login` — the developer-side half of
// the RFC 8628 device-flow (ADR-055 M1.2 handshake + M1.5 CLI).
//
// Flow:
//
//  1. POST /api/dev-pair/device-code → get user_code + device_code.
//  2. Print the user_code and open the verification URI in a browser.
//  3. Poll /api/dev-pair/poll until approved, expired, or interrupted.
//  4. Write ~/.konstera/credentials.json with the minted JWT + metadata.
//  5. Fan-out MCP server configs to every detected coding-agent config
//     path (Cursor, Claude Desktop, Claude Code, Codex, Windsurf,
//     Cline, Continue — see login.KnownTargets).
//
// Nothing in this file does cryptography or stores secrets anywhere
// outside ~/.konstera/*; the Platform API owns the handshake.
func newLoginCmd() *cobra.Command {
	var (
		apiURL              string
		clientName          string
		requestedScopesCSV  string
		suggestedTenantSlug string
		skipFanout          bool
		force               bool
	)
	cmd := &cobra.Command{
		Use:   "login",
		Short: "Pair this machine to a Konstera tenant and configure your coding agent",
		Long: `Pair this machine to a Konstera tenant via the RFC 8628 device-flow.

A browser opens on the Konstera portal with a short code; a tenant admin
reviews what you asked for and approves. The CLI then stores a scoped
access token under ~/.konstera/credentials.json and writes an MCP server
entry into every supported coding-agent config path on this machine
(Cursor, Claude Desktop, Claude Code, OpenAI Codex, Windsurf, Cline,
Continue). Your IDE lights up with Konstera MCP tools next time you
restart it.

Default scope is 'devx.metadata.read' — your IDE can see tenant shape
(connectors + capability tags, LLM engines, glossary) but cannot deploy
or run anything. Request more scopes with --scopes; the admin can trim
before approving.

Examples:
  konstera login
  konstera login --api-url http://localhost:4500
  konstera login --scopes devx.metadata.read,devx.manifest.validate
  konstera login --tenant acme-dev
`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runLogin(cmd.Context(), cmd.OutOrStdout(), cmd.ErrOrStderr(), loginOpts{
				APIURL:              apiURL,
				ClientName:          clientName,
				RequestedScopes:     splitCSV(requestedScopesCSV),
				SuggestedTenantSlug: suggestedTenantSlug,
				SkipFanout:          skipFanout,
				Force:               force,
			})
		},
	}
	cmd.Flags().StringVar(&apiURL, "api-url", envOrDefault("KONSTERA_API_URL", "https://api.konstera.ai"),
		"Konstera Platform API URL. Overridable via KONSTERA_API_URL.")
	cmd.Flags().StringVar(&clientName, "client", defaultClientName(),
		"Client identifier recorded on the pairing (admin UI shows this). Defaults to konstera-cli-<os>.")
	cmd.Flags().StringVar(&requestedScopesCSV, "scopes", "devx.metadata.read",
		"Comma-separated scopes to request. Admin can trim before approving.")
	cmd.Flags().StringVar(&suggestedTenantSlug, "tenant", "",
		"Suggested tenant slug (admin UI pre-selects this; non-authoritative).")
	cmd.Flags().BoolVar(&skipFanout, "no-fanout", false,
		"Skip writing MCP configs into coding-agent config paths; only save credentials.")
	cmd.Flags().BoolVar(&force, "force", false,
		"Overwrite existing konstera-devx MCP entries without prompting (default: silent overwrite of our own key is already on).")
	return cmd
}

type loginOpts struct {
	APIURL              string
	ClientName          string
	RequestedScopes     []string
	SuggestedTenantSlug string
	SkipFanout          bool
	Force               bool
}

func runLogin(ctx context.Context, stdout, stderr io.Writer, opts loginOpts) error {
	out := stdout
	errOut := stderr

	if opts.APIURL == "" {
		return errors.New("--api-url is empty; set it or KONSTERA_API_URL")
	}
	if len(opts.RequestedScopes) == 0 {
		return errors.New("--scopes is empty; request at least one scope (default: devx.metadata.read)")
	}

	fingerprint, err := login.MachineFingerprint()
	if err != nil {
		return fmt.Errorf("compute machine fingerprint: %w", err)
	}

	client := login.NewClient(opts.APIURL)
	init, err := client.Initiate(ctx, login.InitiateRequest{
		ClientName:          opts.ClientName,
		ClientVersion:       version.Version,
		MachineFingerprint:  fingerprint,
		RequestedScopes:     opts.RequestedScopes,
		SuggestedTenantSlug: opts.SuggestedTenantSlug,
	})
	if err != nil {
		return err
	}

	fmt.Fprintln(out)
	fmt.Fprintln(out, "To pair this machine with Konstera:")
	fmt.Fprintln(out)
	fmt.Fprintf(out,  "  1. Open  %s\n", init.VerificationURI)
	fmt.Fprintf(out,  "  2. Enter %s\n", init.UserCode)
	fmt.Fprintln(out)
	if err := openBrowser(init.VerificationURIComplete); err != nil {
		fmt.Fprintln(errOut, "(couldn't open your browser automatically — open the URL above manually)")
	} else {
		fmt.Fprintln(out, "Opened your browser to the approval page.")
	}
	fmt.Fprint(out, "Waiting for approval ")

	poll, err := client.PollUntilApproved(ctx, init, out)
	if err != nil {
		switch {
		case errors.Is(err, login.ErrPollExpired):
			return errors.New("pairing code expired without approval — re-run `konstera login`")
		case errors.Is(err, login.ErrPollAlreadyConsumed):
			return errors.New("that pairing code has already been claimed — re-run `konstera login`")
		default:
			return err
		}
	}

	// Persist credentials.
	creds := &login.Credentials{
		APIBaseURL:         opts.APIURL,
		TenantID:           poll.TenantID,
		TenantSlug:         poll.TenantSlug,
		TenantDisplayName:  poll.TenantDisplayName,
		PairingID:          poll.PairingID,
		AccessToken:        poll.AccessToken,
		RefreshToken:       poll.RefreshToken,
		ExpiresAt:          poll.ExpiresAt,
		GrantedScopes:      poll.GrantedScopes,
		ClientName:         opts.ClientName,
		MachineFingerprint: fingerprint,
		PairedAt:           time.Now(),
	}
	if err := login.SaveCredentials(creds); err != nil {
		return fmt.Errorf("save credentials: %w", err)
	}
	credsPath, _ := login.CredentialsPath()

	fmt.Fprintln(out)
	fmt.Fprintf(out, "Paired with %s (%s).\n", poll.TenantDisplayName, poll.TenantSlug)
	fmt.Fprintf(out, "Credentials saved to %s\n", credsPath)
	fmt.Fprintf(out, "Granted scopes: %s\n", strings.Join(poll.GrantedScopes, ", "))

	if opts.SkipFanout {
		fmt.Fprintln(out, "(--no-fanout) skipping MCP config writes.")
		return nil
	}

	fmt.Fprintln(out)
	fmt.Fprintln(out, "Configuring coding agents:")
	res, err := login.WriteMCPConfigs(creds, opts.Force, out)
	if err != nil {
		return fmt.Errorf("fan-out MCP configs: %w", err)
	}
	if len(res.Skipped) > 0 {
		fmt.Fprintf(out, "  (skipped — not installed: %s)\n", strings.Join(res.Skipped, ", "))
	}
	for _, e := range res.Errors {
		fmt.Fprintf(errOut, "  ! %s\n", e)
	}
	if len(res.Wrote) == 0 && len(res.Errors) == 0 {
		fmt.Fprintln(out)
		fmt.Fprintln(out, "No supported coding agents detected on this machine. Install Cursor, Claude Desktop, Claude Code,")
		fmt.Fprintln(out, "OpenAI Codex, Windsurf, Cline, or Continue and re-run `konstera login` to configure them.")
		return nil
	}

	fmt.Fprintln(out)
	fmt.Fprintln(out, "Restart your IDE to pick up the new MCP server.")
	return nil
}

// ─── helpers ─────────────────────────────────────────────────

func envOrDefault(name, def string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return def
}

func splitCSV(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func defaultClientName() string {
	return "konstera-cli-" + runtime.GOOS
}

func openBrowser(url string) error {
	var cmdName string
	var args []string
	switch runtime.GOOS {
	case "darwin":
		cmdName = "open"
		args = []string{url}
	case "linux":
		cmdName = "xdg-open"
		args = []string{url}
	case "windows":
		cmdName = "rundll32"
		args = []string{"url.dll,FileProtocolHandler", url}
	default:
		return fmt.Errorf("unsupported platform for browser open: %s", runtime.GOOS)
	}
	return exec.Command(cmdName, args...).Start()
}
