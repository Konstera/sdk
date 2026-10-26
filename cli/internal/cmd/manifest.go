package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/Konstera/sdk/cli/internal/manifest"
	"github.com/spf13/cobra"
)

func newManifestCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "manifest",
		Short: "Work with agent manifest files",
	}
	cmd.AddCommand(newManifestValidateCmd())
	return cmd
}

func newManifestValidateCmd() *cobra.Command {
	var schemaPath string
	cmd := &cobra.Command{
		Use:   "validate <path>",
		Short: "Validate an agent manifest against agent-manifest.v3.json",
		Long: `Validate an agent manifest file against the agent-manifest.v3 schema.

Exits 0 on valid manifests, 1 on invalid. Prints a list of schema violations
grouped by JSON pointer for easy fixing.

By default the schema is read from the vendored copy at
  sdk/schemas/agent-manifest.v3.json
Override with --schema if you're validating against a modified copy.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			out := cmd.OutOrStdout()
			manifestPath := args[0]

			if _, err := os.Stat(manifestPath); err != nil {
				return fmt.Errorf("manifest file %s: %w", manifestPath, err)
			}

			resolvedSchema, err := resolveSchemaPath(schemaPath)
			if err != nil {
				return err
			}

			result, err := manifest.Validate(resolvedSchema, manifestPath)
			if err != nil {
				return fmt.Errorf("validator: %w", err)
			}

			if result.Valid() {
				fmt.Fprintf(out, "OK — %s is a valid agent manifest.\n", manifestPath)
				return nil
			}

			fmt.Fprintf(out, "INVALID — %s has %d schema violation(s):\n\n", manifestPath, len(result.Errors()))
			for _, verr := range result.Errors() {
				fmt.Fprintf(out, "  %s\n    %s\n\n", verr.Field(), verr.Description())
			}
			return fmt.Errorf("validation failed")
		},
	}
	cmd.Flags().StringVar(&schemaPath, "schema", "", "Override path to agent-manifest.v3.json (default: vendored copy)")
	return cmd
}

// resolveSchemaPath finds the manifest schema. Order:
//  1. --schema flag if set
//  2. KONSTERA_SCHEMA_DIR env var + /agent-manifest.v3.json
//  3. walking up from CWD looking for a sibling `schemas/agent-manifest.v3.json`
func resolveSchemaPath(flagPath string) (string, error) {
	if flagPath != "" {
		return filepath.Abs(flagPath)
	}
	if envDir := os.Getenv("KONSTERA_SCHEMA_DIR"); envDir != "" {
		return filepath.Join(envDir, "agent-manifest.v3.json"), nil
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := cwd
	for i := 0; i < 10; i++ {
		candidate := filepath.Join(dir, "schemas", "agent-manifest.v3.json")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return "", fmt.Errorf("could not locate agent-manifest.v3.json. Set --schema or KONSTERA_SCHEMA_DIR, or run from inside the sdk/ tree")
}
