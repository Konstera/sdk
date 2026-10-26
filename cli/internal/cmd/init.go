package cmd

import (
	"fmt"

	"github.com/Konstera/sdk/cli/internal/scaffold"
	"github.com/spf13/cobra"
)

func newInitCmd() *cobra.Command {
	var (
		template string
		language string
		dir      string
		force    bool
	)
	cmd := &cobra.Command{
		Use:   "init <name>",
		Short: "Scaffold a new Konstera agent",
		Long: `Scaffold a new Konstera agent in the chosen language.

Creates a folder with the three files every agent ships with:
  - the handler (main.py / Program.cs / src/index.ts)
  - the manifest (manifest.json conforming to agent-manifest.v3.json)
  - the Dockerfile (multi-stage build)

Templates (v0.1):
  hello-world   — minimum shape, one handle() method, one log call

Languages: python | typescript | dotnet

Example:
  konstera init my-first-agent --language python
  cd my-first-agent
  konstera manifest validate manifest.json
  konstera build
`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			out := cmd.OutOrStdout()
			name := args[0]

			if err := scaffold.Create(scaffold.Options{
				Name:     name,
				Language: language,
				Template: template,
				Dir:      dir,
				Force:    force,
			}); err != nil {
				return err
			}

			target := dir
			if target == "" {
				target = name
			}

			fmt.Fprintf(out, "Created %s/ — a %s Konstera agent.\n", target, language)
			fmt.Fprintln(out)
			fmt.Fprintln(out, "Next:")
			fmt.Fprintf(out, "  cd %s\n", target)
			fmt.Fprintln(out, "  konstera manifest validate manifest.json")
			fmt.Fprintln(out, "  konstera build")
			fmt.Fprintln(out)
			fmt.Fprintln(out, "Docs: https://konstera.ai/docs/sdk-quickstart")
			return nil
		},
	}
	cmd.Flags().StringVarP(&template, "template", "t", "hello-world", "Scaffold template")
	cmd.Flags().StringVarP(&language, "language", "l", "python", "Agent language (python | typescript | dotnet)")
	cmd.Flags().StringVar(&dir, "dir", "", "Output directory (defaults to <name>)")
	cmd.Flags().BoolVar(&force, "force", false, "Allow writing into a non-empty directory")
	return cmd
}
