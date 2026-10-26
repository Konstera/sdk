package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func newDevCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "dev",
		Short: "Run a local Konstera dev stack (Compose-based)",
	}
	cmd.AddCommand(
		&cobra.Command{
			Use:   "up",
			Short: "Start the local dev stack (kernel + Postgres + your agent)",
			RunE: func(cmd *cobra.Command, _ []string) error {
				fmt.Fprintln(cmd.OutOrStdout(), "konstera dev up — not implemented in v0.1.")
				fmt.Fprintln(cmd.OutOrStdout())
				fmt.Fprintln(cmd.OutOrStdout(), "For now, use the Konstera platform repo's compose stack:")
				fmt.Fprintln(cmd.OutOrStdout(), "  cd /path/to/platform && docker compose up -d")
				return nil
			},
		},
		&cobra.Command{
			Use:   "down",
			Short: "Stop the local dev stack",
			RunE: func(cmd *cobra.Command, _ []string) error {
				fmt.Fprintln(cmd.OutOrStdout(), "konstera dev down — not implemented in v0.1.")
				return nil
			},
		},
	)
	return cmd
}
