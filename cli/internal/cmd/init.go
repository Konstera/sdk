package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

func newInitCmd() *cobra.Command {
	var (
		template string
		language string
	)
	cmd := &cobra.Command{
		Use:   "init <name>",
		Short: "Scaffold a new Konstera agent",
		Long: `Scaffold a new Konstera agent in the chosen language.

Creates a folder with the three files every agent ships with:
  - the handler (main.py / Program.cs / index.ts)
  - the manifest (manifest.json conforming to agent-manifest.v3.json)
  - the Dockerfile (multi-stage build)

Templates:
  hello-world  — minimum shape, one handle() method
  customer-service-starter — ticket-driven agent with HITL review
  rag-starter   — document-retrieval + answer-with-citations agent
`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			out := cmd.OutOrStdout()
			fmt.Fprintln(out, "konstera init — not implemented in v0.1.")
			fmt.Fprintln(out)
			fmt.Fprintln(out, "For now, clone a reference agent:")
			fmt.Fprintln(out, "  git clone https://github.com/Konstera/agents.git")
			fmt.Fprintln(out)
			fmt.Fprintf(out, "Then copy agents/hello-world-%s/ as your starting point.\n", language)
			fmt.Fprintln(out)
			fmt.Fprintln(out, "Track progress: https://github.com/Konstera/sdk/issues/konstera-cli-init")
			return nil
		},
	}
	cmd.Flags().StringVarP(&template, "template", "t", "hello-world", "Scaffold template")
	cmd.Flags().StringVarP(&language, "language", "l", "python", "Agent language (python | typescript | dotnet)")
	return cmd
}
