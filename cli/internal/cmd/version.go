package cmd

import (
	"fmt"

	"github.com/Konstera/sdk/cli/internal/version"
	"github.com/spf13/cobra"
)

func newVersionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "Print the CLI version",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			out := cmd.OutOrStdout()
			fmt.Fprintf(out, "konstera %s\n", version.Version)
			fmt.Fprintf(out, "  commit: %s\n", version.Commit)
			fmt.Fprintf(out, "  built:  %s\n", version.Date)
			return nil
		},
	}
}
