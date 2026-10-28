package manifest

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"
)

// PortabilityLint checks a manifest for patterns that make agents less
// portable across tenants (ADR-055 §Decision 7). An agent manifest that
// hardcodes a connector *instance* (e.g. "shopify-eu-prod-01") can only
// install on a tenant that happens to have a connector by that exact name;
// a manifest that references a *capability* ("retail.catalog") installs on
// any tenant that exposes that capability. The capability-resolver at
// install time binds capability → instance, keeping agents portable from
// dev tenants to prod and from one tenant's connector stack to another's.
//
// The schema already deprecates `connectionRequirements` in favour of
// `capabilities.needs[]`. This lint turns that deprecation into a hard
// gate at `konstera build` time, with a clearly-signposted migration path
// and an explicit opt-out for teams in the middle of migrating.

// LintOptions configures the lint.
type LintOptions struct {
	// AllowDeprecatedConnectionRequirements lets a build pass even when the
	// manifest still uses the deprecated connectionRequirements[] pattern.
	// Intended as a short-term escape hatch for teams migrating; the long-
	// name flag is deliberately verbose to discourage casual use.
	AllowDeprecatedConnectionRequirements bool
}

// LintIssue is one violation.
type LintIssue struct {
	Rule    string // short identifier, e.g. "deprecated_connection_requirements"
	Message string // human-readable, imperative; names the fix
	// Pointer: dotted JSON path to the offending node (for IDE integrations).
	Pointer string
}

// LintReport is the result of a lint pass.
type LintReport struct {
	Issues []LintIssue
}

// Err returns a formatted error if there are issues, or nil if clean.
func (r *LintReport) Err() error {
	if len(r.Issues) == 0 {
		return nil
	}
	var sb strings.Builder
	sb.WriteString("manifest portability lint failed (ADR-055 §Decision 7):\n")
	for i, issue := range r.Issues {
		fmt.Fprintf(&sb, "  %d. [%s] %s\n", i+1, issue.Rule, issue.Message)
		if issue.Pointer != "" {
			fmt.Fprintf(&sb, "     at: %s\n", issue.Pointer)
		}
	}
	sb.WriteString("\nSee https://konstera.ai/docs/latest/capabilities for the migration guide.\n")
	sb.WriteString("Short-term override: --allow-deprecated-connection-requirements (will not be accepted on package upload).\n")
	return fmt.Errorf("%s", sb.String())
}

// Portability reads the manifest at path, applies the portability lint,
// and returns a report. A read / parse error is returned directly; lint
// violations show up on the returned report's Issues slice.
func Portability(manifestPath string, opts LintOptions) (*LintReport, error) {
	body, err := os.ReadFile(manifestPath)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}
	var raw map[string]any
	if err := json.Unmarshal(body, &raw); err != nil {
		return nil, fmt.Errorf("parse manifest: %w", err)
	}

	report := &LintReport{}

	connReqs, hasConnReqs := raw["connectionRequirements"]
	caps, hasCaps := extractCapabilityNeeds(raw)

	// Rule 1 — deprecated field present. The schema already says this is
	// deprecated (per ADR-013); ADR-055 M1.6 turns the deprecation into
	// a build-time error so new agents cannot ship against it.
	if hasConnReqs && !opts.AllowDeprecatedConnectionRequirements {
		report.Issues = append(report.Issues, LintIssue{
			Rule: "deprecated_connection_requirements",
			Message: "manifest uses `connectionRequirements[]`, which is deprecated per ADR-013. " +
				"Migrate to `capabilities.needs[]` so the agent is portable across tenants " +
				"(the capability resolver binds capability → connector at install time). " +
				"Example: {\"capabilities\":{\"needs\":[{\"name\":\"retail.catalog\",\"required\":true}]}}.",
			Pointer: "$.connectionRequirements",
		})
	}

	// Rule 2 — even with the opt-out, flag entries that look like
	// connector *instance* IDs rather than connector *types*. Heuristic:
	// instance IDs tend to carry environment / numeric / regional suffixes;
	// type slugs are short lowercase words. We flag likely instance IDs
	// loudly; the build still passes under the opt-out but the warning is
	// unmissable in the output.
	if hasConnReqs {
		if arr, ok := connReqs.([]any); ok {
			for i, item := range arr {
				if obj, ok := item.(map[string]any); ok {
					if types, ok := obj["acceptableTypes"].([]any); ok {
						for j, t := range types {
							if s, ok := t.(string); ok && looksLikeConnectorInstance(s) {
								report.Issues = append(report.Issues, LintIssue{
									Rule: "connector_instance_hardcoded",
									Message: fmt.Sprintf(
										"`%s` looks like a connector instance id (environment / "+
											"numeric / regional suffix), not a connector type. Replace "+
											"with a capability from the platform catalogue so this agent "+
											"stays portable across tenants.",
										s),
									Pointer: fmt.Sprintf("$.connectionRequirements[%d].acceptableTypes[%d]", i, j),
								})
							}
						}
					}
				}
			}
		}
	}

	// Rule 3 — advisory: no capabilities.needs[] at all. We don't fail on
	// this unless connectionRequirements is also missing (an agent with
	// zero platform integration — fine, but surface it so authors notice).
	if !hasCaps && !hasConnReqs {
		// Not a lint error — some agents are legitimately standalone.
		// Noted here as a future hook; no issue appended.
		_ = caps
	}

	return report, nil
}

// extractCapabilityNeeds returns true if the manifest declares at least
// one entry under capabilities.needs[].
func extractCapabilityNeeds(raw map[string]any) ([]any, bool) {
	cap, ok := raw["capabilities"].(map[string]any)
	if !ok {
		return nil, false
	}
	needs, ok := cap["needs"].([]any)
	if !ok || len(needs) == 0 {
		return nil, false
	}
	return needs, true
}

// looksLikeConnectorInstance is a heuristic. We err on the side of flagging
// a false-positive (which can be dismissed via the opt-out) over letting
// a real instance-id hardcode slip through (which strands the agent on
// one tenant). Patterns that suggest an instance rather than a type:
//
//   - trailing environment token: `-prod`, `-dev`, `-staging`, `-test`,
//     `-local`, `-main`, `-primary`, `-secondary`
//   - trailing numeric suffix: `-01`, `_02`
//   - UUID anywhere in the string
//   - trailing region code: `-eu`, `-us`, `-apac`, `-emea`, `-uk`, `-de`,
//     etc. (two- or three-letter)
//
// A clean type slug like `shopify`, `postgres`, `rest`, `freshdesk`,
// `klaviyo` has none of these.
var (
	envSuffixRe = regexp.MustCompile(`(?i)[-_](prod|dev|staging|test|local|main|primary|secondary|preprod|uat|qa)$`)
	numericRe   = regexp.MustCompile(`[-_]\d+$`)
	uuidRe      = regexp.MustCompile(`[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`)
	regionRe    = regexp.MustCompile(`(?i)[-_](eu|us|apac|emea|uk|de|fr|jp|cn|in|au|ca|br)$`)
)

func looksLikeConnectorInstance(s string) bool {
	switch {
	case envSuffixRe.MatchString(s):
		return true
	case numericRe.MatchString(s):
		return true
	case uuidRe.MatchString(strings.ToLower(s)):
		return true
	case regionRe.MatchString(s):
		return true
	}
	return false
}
