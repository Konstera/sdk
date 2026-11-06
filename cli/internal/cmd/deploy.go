package cmd

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"strings"

	"github.com/spf13/cobra"

	build "github.com/Konstera/sdk/cli/internal/imagebuild"
	"github.com/Konstera/sdk/cli/internal/login"
	"github.com/Konstera/sdk/cli/internal/mcpbridge"
	"github.com/Konstera/sdk/cli/internal/version"
)

const deployScope = "devx.agent.deploy_dev"

type deployOptions struct {
	manifestPath                          string
	image                                 string
	contextDir                            string
	dockerfile                            string
	platform                              string
	noBuild                               bool
	allowDeprecatedConnectionRequirements bool
}

func newDeployCmd() *cobra.Command {
	var o deployOptions
	cmd := &cobra.Command{
		Use:   "deploy",
		Short: "Build, push and publish the agent to your Konstera workspace",
		Long: `Build, push and publish the agent to the workspace you paired with 'konstera login'.

  1. Builds the image and pushes it to --image (or runtime.image in the
     manifest). It must be a registry your Konstera workspace can pull from:
     a public image (e.g. ghcr.io/you/agent:0.1.0), or localhost:4505/... for
     a local Konstera stack.
  2. Validates the manifest against the workspace and publishes it with
     runtime.image set to that image (agent_publish, idempotent per version).
  3. The agent then shows in the portal under Agents › Catalog, ready to install.

Needs a pairing with the ` + deployScope + ` scope:
  konstera login --scopes devx.metadata.read,devx.manifest.validate,` + deployScope + `

Examples:
  konstera deploy --image ghcr.io/acme/order-helper:0.1.0
  konstera deploy --no-build          # image already pushed; publish only`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runDeploy(cmd.Context(), cmd.OutOrStdout(), cmd.ErrOrStderr(), o)
		},
	}
	cmd.Flags().StringVar(&o.manifestPath, "manifest", "./manifest.json", "Path to manifest.json")
	cmd.Flags().StringVar(&o.image, "image", "", "Image to push and publish, <registry>/<repo>:<tag> (default: runtime.image from the manifest)")
	cmd.Flags().StringVar(&o.contextDir, "context", "", "Docker build context (default: manifest's directory)")
	cmd.Flags().StringVar(&o.dockerfile, "dockerfile", "", "Path to Dockerfile (default: <context>/Dockerfile)")
	cmd.Flags().StringVar(&o.platform, "platform", "", "Target platform (default linux/amd64 for a hosted workspace)")
	cmd.Flags().BoolVar(&o.noBuild, "no-build", false, "Skip build and push; publish an image that is already pushed")
	cmd.Flags().BoolVar(&o.allowDeprecatedConnectionRequirements, "allow-deprecated-connection-requirements", false,
		"Same escape hatch as 'konstera build'")
	return cmd
}

func runDeploy(ctx context.Context, out, errOut io.Writer, o deployOptions) error {
	if ctx == nil {
		ctx = context.Background()
	}
	creds, err := login.LoadCredentials()
	if err != nil || creds == nil || creds.RefreshToken == "" {
		return errors.New("not signed in. Run: konstera login --scopes devx.metadata.read,devx.manifest.validate," + deployScope)
	}
	if !hasScope(creds.GrantedScopes, deployScope) {
		return fmt.Errorf("this pairing can't publish agents (it lacks %s). Run: konstera login --scopes devx.metadata.read,devx.manifest.validate,%s and ask a workspace admin to approve it", deployScope, deployScope)
	}

	raw, err := os.ReadFile(o.manifestPath)
	if err != nil {
		return fmt.Errorf("read manifest: %w", err)
	}
	var manifest map[string]any
	if err := json.Unmarshal(raw, &manifest); err != nil {
		return fmt.Errorf("%s is not valid JSON: %w", o.manifestPath, err)
	}
	runtimeSection, _ := manifest["runtime"].(map[string]any)
	if runtimeSection == nil {
		return fmt.Errorf("%s has no runtime section", o.manifestPath)
	}
	image := strings.TrimSpace(o.image)
	if image == "" {
		image, _ = runtimeSection["image"].(string)
	}
	if err := checkDeployImage(image, creds.APIBaseURL); err != nil {
		return err
	}

	if !o.noBuild {
		platform := o.platform
		if platform == "" && !isLocalAPI(creds.APIBaseURL) {
			// Hosted workspaces run linux/amd64 nodes; an arm64 laptop build would not start there.
			platform = "linux/amd64"
		}
		if err := build.Run(build.Options{
			ManifestPath: o.manifestPath, Context: o.contextDir, Dockerfile: o.dockerfile,
			Tag: image, Push: true, Platform: platform,
			AllowDeprecatedConnectionRequirements: o.allowDeprecatedConnectionRequirements,
			Stdout:                                out, Stderr: errOut,
		}); err != nil {
			return fmt.Errorf("build and push failed: %w", err)
		}
	}

	if prev, _ := runtimeSection["image"].(string); prev != image {
		fmt.Fprintf(out, "Publishing with runtime.image = %s (your manifest.json says %q; update it to match).\n", image, prev)
	}
	runtimeSection["image"] = image
	body, err := json.Marshal(manifest)
	if err != nil {
		return err
	}

	credPath, err := login.CredentialsPath()
	if err != nil {
		return err
	}
	remote := mcpbridge.NewRemote(creds.APIBaseURL,
		mcpbridge.NewSession(credPath, login.NewClient(creds.APIBaseURL)), "konstera-cli", version.Version)
	text, isError, err := callTool(ctx, remote, "agent_publish", map[string]any{"manifestJson": string(body)})
	if err != nil {
		return fmt.Errorf("publish: %w", err)
	}
	if isError {
		return fmt.Errorf("publish refused: %s", text)
	}
	return reportPublish(out, text, creds)
}

// callTool runs one /mcp/devx tool and returns its text content.
func callTool(ctx context.Context, remote *mcpbridge.Remote, name string, args map[string]any) (string, bool, error) {
	result, err := remote.Call(ctx, "tools/call", map[string]any{"name": name, "arguments": args})
	if err != nil {
		return "", false, err
	}
	var r struct {
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
		IsError bool `json:"isError"`
	}
	if err := json.Unmarshal(result, &r); err != nil {
		return "", false, fmt.Errorf("unexpected reply: %w", err)
	}
	var parts []string
	for _, c := range r.Content {
		if c.Type == "text" {
			parts = append(parts, c.Text)
		}
	}
	return strings.Join(parts, "\n"), r.IsError, nil
}

func reportPublish(out io.Writer, text string, creds *login.Credentials) error {
	var p struct {
		Published bool   `json:"published"`
		Reason    string `json:"reason"`
		Errors    []struct {
			Path    string `json:"path"`
			Message string `json:"message"`
		} `json:"errors"`
		AgentID string `json:"agentId"`
		Version string `json:"version"`
		Name    string `json:"name"`
		Action  string `json:"action"`
	}
	if err := json.Unmarshal([]byte(text), &p); err != nil {
		return fmt.Errorf("unexpected publish reply: %s", text)
	}
	if !p.Published {
		lines := []string{"the manifest is not valid for this workspace:"}
		for _, e := range p.Errors {
			lines = append(lines, fmt.Sprintf("  %s: %s", e.Path, e.Message))
		}
		return errors.New(strings.Join(lines, "\n"))
	}
	workspace := creds.TenantDisplayName
	if workspace == "" {
		workspace = creds.TenantSlug
	}
	fmt.Fprintf(out, "Published %s %s to %s (%s).\n", p.AgentID, p.Version, workspace, p.Action)
	fmt.Fprintln(out, "Next: install it in the portal under Agents › Catalog, then bind its capabilities to connections.")
	return nil
}

// checkDeployImage wants a full reference with a registry host, and refuses
// a localhost registry for a hosted workspace (it can't pull from your machine).
func checkDeployImage(image, apiBase string) error {
	if image == "" {
		return errors.New("no image to publish: pass --image <registry>/<repo>:<tag> or set runtime.image in the manifest")
	}
	first := strings.SplitN(image, "/", 2)[0]
	hasRegistry := strings.Contains(image, "/") && (strings.ContainsAny(first, ".:") || first == "localhost")
	if !hasRegistry {
		return fmt.Errorf("image %q has no registry. Use a full reference Konstera can pull, e.g. ghcr.io/you/%s", image, image)
	}
	if !strings.Contains(image[strings.LastIndex(image, "/")+1:], ":") && !strings.Contains(image, "@") {
		return fmt.Errorf("image %q has no tag; add one, e.g. :0.1.0", image)
	}
	host := strings.SplitN(first, ":", 2)[0]
	if (host == "localhost" || host == "127.0.0.1") && !isLocalAPI(apiBase) {
		return fmt.Errorf("image %q is in a registry on your machine, which %s can't pull from. Push to a registry it can reach (e.g. a public ghcr.io image)", image, apiBase)
	}
	return nil
}

func isLocalAPI(base string) bool {
	u, err := url.Parse(base)
	if err != nil {
		return false
	}
	h := u.Hostname()
	return h == "localhost" || h == "127.0.0.1" || h == "::1"
}
