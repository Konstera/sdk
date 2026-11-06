package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/mcpbridge"
)

// secretsScope is the pairing scope the upload needs (Konstera maps it to
// the credentials.rotate permission).
const secretsScope = "devx.connections.secrets"

// maxSecretsFile matches the server's body limit.
const maxSecretsFile = 64 * 1024

func newConnectionCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "connection",
		Short: "Work with the workspace's connections",
		Long: `Work with the workspace's connections (links to outside systems).

Create and look after connections from your coding agent over MCP
(connection_create, connection_test, …). Secrets never go through the chat:
save them in a local file and upload it with 'konstera connection secret'.`,
	}
	cmd.AddCommand(newConnectionSecretCmd())
	return cmd
}

func newConnectionSecretCmd() *cobra.Command {
	var file string
	var keep bool
	cmd := &cobra.Command{
		Use:   "secret <alias>",
		Short: "Upload a connection's secrets from a local file",
		Long: `Upload a connection's secrets from a local file, then test the connection.

The file is a JSON object with one string per credential field, e.g.

  {
    "api_token": "…",
    "email": "support@acme.example"
  }

Your coding agent tells you the field names (connection_create /
connection_describe). The default file is ~/.konstera/secrets/<alias>.json.
It is uploaded over HTTPS and deleted once the connection test passes
(use --keep to keep it). If the test fails the file stays so you can fix it.
The values are never printed.

Needs a pairing with the ` + secretsScope + ` scope:
  konstera login --scopes devx.metadata.read,` + secretsScope,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return runConnectionSecret(cmd.Context(), cmd.OutOrStdout(), args[0], file, keep)
		},
	}
	cmd.Flags().StringVar(&file, "file", "", "Secrets file (default ~/.konstera/secrets/<alias>.json)")
	cmd.Flags().BoolVar(&keep, "keep", false, "Keep the file after a successful upload")
	return cmd
}

// secretsFileName is the default file name for an alias. Same rule as the
// platform (ConnectionSecretFields.FileName), so the path the agent shows
// is the path the CLI reads.
func secretsFileName(alias string) string {
	var b strings.Builder
	for _, r := range strings.ToLower(strings.TrimSpace(alias)) {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' || r == '_' {
			b.WriteRune(r)
		} else {
			b.WriteRune('-')
		}
	}
	return b.String() + ".json"
}

func defaultSecretsPath(alias string) (string, error) {
	home, err := login.KonsteraHome()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "secrets", secretsFileName(alias)), nil
}

// readSecretsFile reads and checks the file. Errors name fields, never values.
func readSecretsFile(path string) (map[string]string, []string, error) {
	var warnings []string
	info, err := os.Stat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil, fmt.Errorf("no secrets file at %s. Create it (a JSON object of field names to values) and run this again", path)
	}
	if err != nil {
		return nil, nil, err
	}
	if info.IsDir() {
		return nil, nil, fmt.Errorf("%s is a folder, not a file", path)
	}
	if info.Size() > maxSecretsFile {
		return nil, nil, fmt.Errorf("%s is too large (64 KB at most)", path)
	}
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o077 != 0 {
		warnings = append(warnings, fmt.Sprintf("%s can be read by other users on this machine (mode %o). It is deleted after the upload; next time create it with chmod 600.", path, info.Mode().Perm()))
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	raw = bytes.TrimPrefix(raw, []byte("\xef\xbb\xbf")) // Notepad's UTF-8 BOM
	var obj map[string]any
	if err := json.Unmarshal(raw, &obj); err != nil {
		// Don't wrap err: the JSON error can quote the file.
		return nil, nil, fmt.Errorf("%s is not a JSON object like {\"api_key\": \"…\"}", path)
	}
	out := make(map[string]string, len(obj))
	for k, v := range obj {
		switch s := v.(type) {
		case string:
			if strings.TrimSpace(s) != "" {
				out[k] = s
			}
		case nil:
		default:
			return nil, nil, fmt.Errorf("%q in %s must be a string (put the value in quotes)", k, path)
		}
	}
	if len(out) == 0 {
		return nil, nil, fmt.Errorf("%s has no values filled in", path)
	}
	return out, warnings, nil
}

type secretsUploadResult struct {
	Saved           []string `json:"saved"`
	MissingRequired []string `json:"missingRequired"`
	Test            struct {
		OK      bool   `json:"ok"`
		Message string `json:"message"`
	} `json:"test"`
}

func runConnectionSecret(ctx context.Context, out io.Writer, alias, file string, keep bool) error {
	if ctx == nil {
		ctx = context.Background()
	}
	alias = strings.TrimSpace(alias)
	if alias == "" {
		return errors.New("give the connection's alias, e.g. konstera connection secret zendesk-support")
	}
	path := file
	if path == "" {
		p, err := defaultSecretsPath(alias)
		if err != nil {
			return err
		}
		path = p
	}

	creds, err := login.LoadCredentials()
	if err != nil || creds == nil || creds.RefreshToken == "" {
		return errors.New("not signed in. Run: konstera login --scopes devx.metadata.read," + secretsScope)
	}
	if !hasScope(creds.GrantedScopes, secretsScope) {
		return fmt.Errorf("this pairing can't upload secrets (it lacks %s). Run: konstera login --scopes devx.metadata.read,%s and ask a workspace admin to approve it", secretsScope, secretsScope)
	}
	if err := checkSecureBase(creds.APIBaseURL); err != nil {
		return err
	}

	secrets, warnings, err := readSecretsFile(path)
	if err != nil {
		return err
	}
	for _, w := range warnings {
		fmt.Fprintln(out, "warning: "+w)
	}

	credPath, err := login.CredentialsPath()
	if err != nil {
		return err
	}
	session := mcpbridge.NewSession(credPath, login.NewClient(creds.APIBaseURL))
	result, err := uploadSecrets(ctx, creds.APIBaseURL, session, alias, secrets)
	if err != nil {
		return err
	}

	sort.Strings(result.Saved)
	fmt.Fprintf(out, "Saved %d secret field(s) on %s: %s\n", len(result.Saved), alias, strings.Join(result.Saved, ", "))
	if len(result.MissingRequired) > 0 {
		fmt.Fprintf(out, "Still missing (required): %s\n", strings.Join(result.MissingRequired, ", "))
	}
	if result.Test.OK {
		fmt.Fprintln(out, "Connection test: OK")
	} else {
		fmt.Fprintf(out, "Connection test failed: %s\n", result.Test.Message)
	}

	if !result.Test.OK {
		// Keep the file so a wrong value can be corrected and uploaded again.
		return fmt.Errorf("the secrets were saved but the connection test failed. Fix the values in %s and run this again", path)
	}
	if !keep {
		if err := shredFile(path); err != nil {
			fmt.Fprintf(out, "warning: uploaded, but couldn't delete %s (%v). Delete it yourself.\n", path, err)
		} else {
			fmt.Fprintf(out, "Deleted %s\n", path)
		}
	}
	return nil
}

func uploadSecrets(ctx context.Context, apiBase string, session *mcpbridge.Session, alias string, secrets map[string]string) (*secretsUploadResult, error) {
	body, err := json.Marshal(map[string]any{"secrets": secrets})
	if err != nil {
		return nil, err
	}
	endpoint := strings.TrimRight(apiBase, "/") + "/mcp/devx/connections/" + url.PathEscape(alias) + "/secrets"
	client := &http.Client{Timeout: 60 * time.Second}

	for attempt := 0; attempt < 2; attempt++ {
		token, err := session.Token(ctx, attempt > 0)
		if err != nil {
			return nil, fmt.Errorf("sign-in expired or was revoked (%v). Run konstera login again", err)
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPut, endpoint, bytes.NewReader(body))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Content-Type", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("couldn't reach Konstera: %w", err)
		}
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		resp.Body.Close()

		switch {
		case resp.StatusCode == http.StatusUnauthorized && attempt == 0:
			continue // renew the token once
		case resp.StatusCode == http.StatusOK:
			var r secretsUploadResult
			if err := json.Unmarshal(raw, &r); err != nil {
				return nil, fmt.Errorf("unexpected answer from Konstera: %w", err)
			}
			return &r, nil
		default:
			return nil, fmt.Errorf("Konstera refused the upload (HTTP %d): %s", resp.StatusCode, errorMessage(raw))
		}
	}
	return nil, errors.New("Konstera refused the sign-in. Run konstera login again")
}

func errorMessage(raw []byte) string {
	var e struct {
		Error   string `json:"error"`
		Message string `json:"message"`
	}
	if json.Unmarshal(raw, &e) == nil {
		if e.Message != "" {
			return e.Message
		}
		if e.Error != "" {
			return e.Error
		}
	}
	return strings.TrimSpace(string(raw))
}

func hasScope(scopes []string, want string) bool {
	for _, s := range scopes {
		if s == want {
			return true
		}
	}
	return false
}

// checkSecureBase refuses to send secrets over plain HTTP, except to this machine.
func checkSecureBase(base string) error {
	u, err := url.Parse(base)
	if err != nil {
		return fmt.Errorf("saved API address %q is not a URL; run konstera login again", base)
	}
	if u.Scheme == "https" {
		return nil
	}
	host := u.Hostname()
	if u.Scheme == "http" && (host == "localhost" || host == "127.0.0.1" || host == "::1") {
		return nil
	}
	return fmt.Errorf("won't send secrets to %s over plain HTTP", base)
}

// shredFile overwrites the file with zeros before deleting it. On SSDs and
// copy-on-write file systems this is best effort; deleting is what counts.
func shredFile(path string) error {
	if info, err := os.Stat(path); err == nil && info.Mode().IsRegular() {
		if f, err := os.OpenFile(path, os.O_WRONLY, 0); err == nil {
			_, _ = f.Write(make([]byte, info.Size()))
			_ = f.Sync()
			_ = f.Close()
		}
	}
	return os.Remove(path)
}
