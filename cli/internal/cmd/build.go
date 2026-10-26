package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func newBuildCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "build",
		Short: "Build the agent container image",
		Long: `Build the agent container image using the Dockerfile in the current directory.

Thin wrapper around 'docker buildx build'. Reads the agent id + version from
manifest.json and tags the image accordingly.
`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			fmt.Fprintln(cmd.OutOrStdout(), "konstera build — not implemented in v0.1.")
			fmt.Fprintln(cmd.OutOrStdout())
			fmt.Fprintln(cmd.OutOrStdout(), "For now, build directly with Docker:")
			fmt.Fprintln(cmd.OutOrStdout(), "  docker buildx build -t <registry>/<id>:<version> .")
			return nil
		},
	}
}
