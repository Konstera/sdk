// Command konstera is the Konstera agent-authoring CLI.
//
// See `konstera --help` for the command surface, or
// https://konstera.ai/docs/sdk-quickstart for the authoring guide.
package main

import (
	"fmt"
	"os"

	"github.com/Konstera/sdk/cli/internal/cmd"
)

func main() {
	if err := cmd.NewRootCmd().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
