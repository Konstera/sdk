package manifest

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
)

// Copy lint: text in a manifest is shown to the people who install and run
// the agent (its description, each model purpose's description, each
// capability's reason, config field descriptions, eval questions). Those
// readers don't have the author's design records or release history, so
// references to them read as noise: "Triage (ADR-030): ...", "(Sub-slice
// B.3)", "migration 115", or a version-by-version history in the agent
// description. Found on a tenant's Models tab in 2026-11; the patterns below
// are the ones that leaked, kept narrow so ordinary prose never trips them.

// CopyIssue is one string that carries an internal reference.
type CopyIssue struct {
	Pointer string // JSON path, e.g. $.llmRequirements[1].description
	Match   string // the text that matched
	Rule    string // short identifier of the pattern
}

var copyRules = []struct {
	rule string
	re   *regexp.Regexp
	fix  string
}{
	{"design_record", regexp.MustCompile(`\bADR-\d+`), "a design-record number"},
	{"work_item", regexp.MustCompile(`\bSub-slice\b`), "a work-item label"},
	{"migration_number", regexp.MustCompile(`\b[Mm]igration \d{2,}\b`), "a database migration number"},
	{"release_history", regexp.MustCompile(`\bv\d+\.\d+\.\d+ \(`), "release history (put it in a CHANGELOG)"},
}

// CopyReport is the result of a copy lint pass.
type CopyReport struct {
	Issues []CopyIssue
}

// Err returns a formatted error if there are issues, or nil if clean.
func (r *CopyReport) Err() error {
	if len(r.Issues) == 0 {
		return nil
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "manifest text lint failed: %d string(s) shown to users carry internal references:\n", len(r.Issues))
	for i, is := range r.Issues {
		fmt.Fprintf(&sb, "  %d. %s: %q (%s)\n", i+1, is.Pointer, is.Match, ruleFix(is.Rule))
	}
	sb.WriteString("\nRewrite these in plain language for the person installing the agent; keep version history in a CHANGELOG.\n")
	sb.WriteString("Override: --allow-internal-refs.\n")
	return fmt.Errorf("%s", sb.String())
}

func ruleFix(rule string) string {
	for _, r := range copyRules {
		if r.rule == rule {
			return r.fix
		}
	}
	return rule
}

// Copy reads the manifest at path and reports every string value that
// matches an internal-reference pattern. Keys are not checked, only values.
func Copy(manifestPath string) (*CopyReport, error) {
	body, err := os.ReadFile(manifestPath)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}
	return CopyFromJSON(body)
}

// CopyFromJSON is Copy on manifest bytes.
func CopyFromJSON(body []byte) (*CopyReport, error) {
	var raw any
	if err := json.Unmarshal(body, &raw); err != nil {
		return nil, fmt.Errorf("parse manifest: %w", err)
	}
	report := &CopyReport{}
	walkStrings(raw, "$", func(ptr, s string) {
		for _, r := range copyRules {
			if m := r.re.FindString(s); m != "" {
				report.Issues = append(report.Issues, CopyIssue{Pointer: ptr, Match: m, Rule: r.rule})
			}
		}
	})
	return report, nil
}

func walkStrings(node any, path string, visit func(ptr, s string)) {
	switch v := node.(type) {
	case map[string]any:
		keys := make([]string, 0, len(v))
		for k := range v {
			keys = append(keys, k)
		}
		sort.Strings(keys) // stable output
		for _, k := range keys {
			walkStrings(v[k], path+"."+k, visit)
		}
	case []any:
		for i, item := range v {
			walkStrings(item, fmt.Sprintf("%s[%d]", path, i), visit)
		}
	case string:
		visit(path, v)
	}
}
