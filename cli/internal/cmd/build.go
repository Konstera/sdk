package cmd

import (
	build "github.com/Konstera/sdk/cli/internal/imagebuild"
	"github.com/spf13/cobra"
)

func newBuildCmd() *cobra.Command {
	var (
		manifestPath                          string
		contextDir                            string
		dockerfile                            string
		tag                                   string
		push                                  bool
		platform                              string
		allowDeprecatedConnectionRequirements bool
	)
	cmd := &cobra.Command{
		Use:   "build",
		Short: "Build the agent container image",
		Long: `Build the agent container image.

Thin wrapper around 'docker buildx build'. Reads id + version from
manifest.json and tags the image as <id>:<version> unless --tag is given.

By default the image is loaded into the local Docker daemon (--load).
Pass --push to push to the registry inferred from --tag instead.

Multi-arch builds: pass --platform (e.g. linux/amd64,linux/arm64). Requires
a configured buildx builder with multi-arch support — docker-container
driver works out of the box.

Examples:
  konstera build
  konstera build --tag ghcr.io/me/my-agent:0.1.0 --push
  konstera build --platform linux/amd64,linux/arm64 --tag ghcr.io/me/x:0.1 --push
`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return build.Run(build.Options{
				ManifestPath:                          manifestPath,
				Context:                               contextDir,
				Dockerfile:                            dockerfile,
				Tag:                                   tag,
				Push:                                  push,
				Platform:                              platform,
				AllowDeprecatedConnectionRequirements: allowDeprecatedConnectionRequirements,
				Stdout:                                cmd.OutOrStdout(),
				Stderr:                                cmd.ErrOrStderr(),
			})
		},
	}
	cmd.Flags().StringVar(&manifestPath, "manifest", "./manifest.json", "Path to manifest.json")
	cmd.Flags().StringVar(&contextDir, "context", "", "Docker build context (default: manifest's directory)")
	cmd.Flags().StringVar(&dockerfile, "dockerfile", "", "Path to Dockerfile (default: <context>/Dockerfile)")
	cmd.Flags().StringVarP(&tag, "tag", "t", "", "Image tag (default: <id>:<version> from manifest)")
	cmd.Flags().BoolVar(&push, "push", false, "Push to the registry after build (instead of --load into local Docker)")
	cmd.Flags().StringVar(&platform, "platform", "", "Target platform(s), e.g. linux/amd64,linux/arm64")
	cmd.Flags().BoolVar(&allowDeprecatedConnectionRequirements, "allow-deprecated-connection-requirements", false,
		"Short-term escape hatch: let the build pass when the manifest still uses `connectionRequirements[]` (deprecated per ADR-013). "+
			"Instance-id heuristics still fire under the opt-out. Packages built with this flag will be refused at upload time once the "+
			"server-side gate ships. Prefer migrating to `capabilities.needs[]`.")
	return cmd
}
