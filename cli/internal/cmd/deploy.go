package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func newDeployCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "deploy",
		Short: "Deploy the agent to a Konstera workspace",
		Long: "Push the agent image to the workspace registry and register the manifest.\n\nRequires 'konstera login' first.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			fmt.Fprintln(cmd.OutOrStdout(), "konstera deploy — not implemented in v0.1.")
			fmt.Fprintln(cmd.OutOrStdout())
			fmt.Fprintln(cmd.OutOrStdout(), "For now, use the portal: Agents > Upload package.")
			return nil
		},
	}
}
