package manifest

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeManifest(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "manifest.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}
	return path
}

func TestPortability_CleanManifest_UsingCapabilitiesNeeds(t *testing.T) {
	path := writeManifest(t, `{
		"id": "demo",
		"version": "0.1.0",
		"capabilities": {"needs": [{"name": "retail.catalog", "required": true}]}
	}`)
	r, err := Portability(path, LintOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Issues) != 0 {
		t.Fatalf("expected zero issues, got %v", r.Issues)
	}
	if r.Err() != nil {
		t.Fatalf("Err() should be nil on clean manifest: %v", r.Err())
	}
}

func TestPortability_DeprecatedField_FailsByDefault(t *testing.T) {
	path := writeManifest(t, `{
		"id": "demo",
		"version": "0.1.0",
		"connectionRequirements": [
			{"purpose": "catalog", "acceptableTypes": ["shopify"]}
		]
	}`)
	r, err := Portability(path, LintOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Issues) == 0 {
		t.Fatalf("expected deprecated_connection_requirements issue, got none")
	}
	if r.Issues[0].Rule != "deprecated_connection_requirements" {
		t.Fatalf("expected rule=deprecated_connection_requirements, got %s", r.Issues[0].Rule)
	}
	if r.Err() == nil {
		t.Fatalf("Err() should be non-nil when issues present")
	}
	if !strings.Contains(r.Err().Error(), "ADR-055") {
		t.Fatalf("Err() should reference ADR-055: %v", r.Err())
	}
}

func TestPortability_DeprecatedField_OptOut_StillFlagsInstanceIDs(t *testing.T) {
	// With the opt-out set, the deprecated-field rule does not fire, but
	// instance-id heuristics still do — the opt-out is for migrations,
	// not for permanently shipping hardcoded instance ids.
	path := writeManifest(t, `{
		"id": "demo",
		"version": "0.1.0",
		"connectionRequirements": [
			{"purpose": "catalog", "acceptableTypes": ["shopify-eu-prod-01"]}
		]
	}`)
	r, err := Portability(path, LintOptions{AllowDeprecatedConnectionRequirements: true})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Issues) != 1 {
		t.Fatalf("expected 1 instance-id issue, got %d: %v", len(r.Issues), r.Issues)
	}
	if r.Issues[0].Rule != "connector_instance_hardcoded" {
		t.Fatalf("expected rule=connector_instance_hardcoded, got %s", r.Issues[0].Rule)
	}
}

func TestPortability_DeprecatedField_OptOut_CleanTypes_Passes(t *testing.T) {
	// Clean type slugs (no instance markers) pass under the opt-out.
	path := writeManifest(t, `{
		"id": "demo",
		"version": "0.1.0",
		"connectionRequirements": [
			{"purpose": "catalog", "acceptableTypes": ["shopify", "woocommerce"]}
		]
	}`)
	r, err := Portability(path, LintOptions{AllowDeprecatedConnectionRequirements: true})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Issues) != 0 {
		t.Fatalf("expected zero issues under opt-out with clean types, got %v", r.Issues)
	}
}

func TestLooksLikeConnectorInstance(t *testing.T) {
	cases := []struct {
		s    string
		want bool
	}{
		// Clean type slugs — must not flag.
		{"shopify", false},
		{"postgres", false},
		{"rest", false},
		{"freshdesk", false},
		{"klaviyo", false},
		{"woocommerce", false},
		{"big_commerce", false},

		// Environment suffixes.
		{"shopify-prod", true},
		{"shopify-dev", true},
		{"shopify-staging", true},
		{"shopify-main", true},
		{"shopify-primary", true},
		{"shopify_prod", true},

		// Numeric suffixes.
		{"shopify-01", true},
		{"shopify_02", true},

		// UUIDs.
		{"shopify-a1b2c3d4-e5f6-7890-abcd-1234567890ab", true},

		// Region suffixes.
		{"shopify-eu", true},
		{"shopify-us", true},
		{"shopify_apac", true},
	}
	for _, c := range cases {
		t.Run(c.s, func(t *testing.T) {
			got := looksLikeConnectorInstance(c.s)
			if got != c.want {
				t.Fatalf("looksLikeConnectorInstance(%q) = %v, want %v", c.s, got, c.want)
			}
		})
	}
}

func TestPortability_InvalidJSON_ReturnsError(t *testing.T) {
	path := writeManifest(t, `not json`)
	_, err := Portability(path, LintOptions{})
	if err == nil {
		t.Fatalf("expected parse error")
	}
}
