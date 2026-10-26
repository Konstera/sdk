// Package cmd wires the Cobra command tree for `konstera`.
package cmd

import (
	"github.com/spf13/cobra"
)

// NewRootCmd builds the root `konstera` command and all its subcommands.
// Each subcommand lives in its own file in this package.
func NewRootCmd() *cobra.Command {
	root := &cobra.Command{
		Use:   "konstera",
		Short: "The Konstera agent-authoring CLI",
		Long: `konstera is the agent-authoring tool for the Konstera platform.

Scaffold, validate, build, and deploy agents that run on Konstera.

Full documentation: https://konstera.ai/docs
Repo: https://github.com/Konstera/sdk/tree/main/cli`,
		SilenceUsage: true, // don't dump --help on every error
	}

	root.AddCommand(
		newVersionCmd(),
		newInitCmd(),
		newManifestCmd(),
		newBuildCmd(),
		newDeployCmd(),
		newDevCmd(),
	)
	return root
}
