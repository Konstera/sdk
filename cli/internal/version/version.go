// Package version holds the CLI's version string, injected at build time
// via `-ldflags "-X github.com/Konstera/sdk/cli/internal/version.Version=X.Y.Z"`.
// GoReleaser sets this automatically from the git tag.
package version

var (
	// Version is the CLI version. "dev" for local builds without ldflags.
	Version = "dev"
	// Commit is the git SHA this binary was built from. Set by GoReleaser.
	Commit = "unknown"
	// Date is the ISO-8601 timestamp of the build. Set by GoReleaser.
	Date = "unknown"
)
